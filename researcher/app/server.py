import logging
import os
import uuid
import warnings
from contextlib import asynccontextmanager

# Suppress experimental warnings for A2A components
warnings.filterwarnings("ignore", message=r".*\[EXPERIMENTAL\].*", category=UserWarning)

# Suppress runner app name mismatch warning
logging.getLogger("google_adk.google.adk.runners").setLevel(logging.ERROR)
logging.getLogger("google.adk.runners").setLevel(logging.ERROR)

# Suppress Google Auth warnings
warnings.filterwarnings("ignore", message=".*Your application has authenticated using end user credentials.*")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from google.adk.artifacts.in_memory_artifact_service import InMemoryArtifactService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types as genai_types
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider, export
from opentelemetry.sdk.trace.export import ConsoleSpanExporter

# A2A Imports
from a2a.server.apps.jsonrpc.fastapi_app import A2AFastAPIApplication
from a2a.server.request_handlers.default_request_handler import DefaultRequestHandler
from a2a.server.tasks.inmemory_task_store import InMemoryTaskStore
from a2a.types import AgentCard
from a2a.server.agent_execution.agent_executor import AgentExecutor
from a2a.server.events.event_queue import EventQueue
from a2a.server.agent_execution.context import RequestContext
from a2a.types import Message, TextPart

from app.agent import app as adk_app

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Telemetry
provider = TracerProvider()
processor = export.SimpleSpanProcessor(ConsoleSpanExporter())
trace.set_tracer_provider(provider)

# Runner Setup
runner = Runner(
    app=adk_app,
    artifact_service=InMemoryArtifactService(),
    session_service=InMemorySessionService(),
)

# --- Custom Executor ---
class AdkToA2aExecutor(AgentExecutor):
    def __init__(self, runner, app_name):
        self.runner = runner
        self.app_name = app_name

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        # 1. Extract User/Session
        user_id = "default_user"
        # Fix: ServerCallContext does not have raw_headers. Check user object or state.
        if context.call_context:
            if hasattr(context.call_context, "user") and context.call_context.user:
                 # If it's an authenticated user object, it might have an id
                 if hasattr(context.call_context.user, "id") and context.call_context.user.id:
                     user_id = context.call_context.user.id
            
            # Fallback: check state for potential headers or info
            if user_id == "default_user" and context.call_context.state:
                 user_id = context.call_context.state.get("user_id", "default_user")

        session_id = context.context_id or "default_session"

        # 2. Convert Input
        user_text = ""
        if context.message and context.message.parts:
            for part in context.message.parts:
                # Direct TextPart
                if isinstance(part, TextPart):
                    user_text += part.text
                # Wrapped TextPart (RootModel)
                elif hasattr(part, "root") and isinstance(part.root, TextPart):
                    user_text += part.root.text
                # Fallbacks
                else:
                    try:
                        if hasattr(part, 'text'):
                            user_text += part.text
                        elif isinstance(part, dict) and 'text' in part:
                            user_text += part['text']
                    except Exception as e:
                        logger.error(f"[{self.app_name}] Error extracting text: {e}")
        
        adk_msg = genai_types.Content(
            role="user", parts=[genai_types.Part.from_text(text=user_text)]
        )

        logger.info(f"[{self.app_name}] Executing task for user={user_id} session={session_id}")

        # 3. Get/Create Session
        try:
            session = await self.runner.session_service.get_session(
                session_id=session_id, app_name=self.app_name, user_id=user_id
            )
        except Exception:
            session = None
            
        if not session:
            session = await self.runner.session_service.create_session(
                app_name=self.app_name, user_id=user_id, session_id=session_id
            )

        # 4. Run Agent
        async for event in self.runner.run_async(
            user_id=user_id, session_id=session.id, new_message=adk_msg
        ):
             # 5. Stream Output
             if event.content and event.content.parts:
                 text_content = ""
                 for p in event.content.parts:
                     if p.text: text_content += p.text
                 
                 if text_content:
                    a2a_msg = Message(
                        messageId=str(uuid.uuid4()),
                        role="agent",
                        parts=[TextPart(text=text_content)]
                    )
                    await event_queue.enqueue_event(a2a_msg)

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        pass

# --- A2A Setup ---
PORT = 8001
task_store = InMemoryTaskStore()
executor = AdkToA2aExecutor(runner, adk_app.name)
request_handler = DefaultRequestHandler(agent_executor=executor, task_store=task_store)

agent_card_data = {
    "name": adk_app.name,
    "description": "Gathers information using Google Search.", 
    "version": "0.1.0",
    "protocolVersion": "0.1.0",
    "url": f"http://localhost:{PORT}/a2a/{adk_app.name}",
    "capabilities": {},
    "security": [],
    "defaultInputModes": ["text"],
    "defaultOutputModes": ["text"],
    "skills": []
}
agent_card = AgentCard(**agent_card_data)

a2a_app = A2AFastAPIApplication(agent_card=agent_card, http_handler=request_handler)

# --- FastAPI App ---
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register A2A routes directly using A2AFastAPIApplication method
a2a_app.add_routes_to_app(
    app=app,
    rpc_url=f"/a2a/{adk_app.name}",
    agent_card_url=f"/.well-known/agent.json"
)

@app.get("/")
def root():
    return {"status": "ok", "service": "researcher", "agent": adk_app.name, "a2a_card": f"http://localhost:{PORT}/.well-known/agent.json"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)