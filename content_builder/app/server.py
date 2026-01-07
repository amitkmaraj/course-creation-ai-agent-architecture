import logging
import os
import warnings
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

# Suppress experimental warnings for A2A components
warnings.filterwarnings("ignore", message=".*\[EXPERIMENTAL\].*", category=UserWarning)

# Suppress runner app name mismatch warning
logging.getLogger("google.adk.runners").setLevel(logging.ERROR)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from google.adk.artifacts.in_memory_artifact_service import InMemoryArtifactService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types as genai_types
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider, export
from opentelemetry.sdk.trace.export import ConsoleSpanExporter
from pydantic import BaseModel

from app.agent import app as adk_app

class Feedback(BaseModel):
    score: float
    text: str | None = None
    run_id: str | None = None
    user_id: str | None = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

provider = TracerProvider()
processor = export.SimpleSpanProcessor(ConsoleSpanExporter())
trace.set_tracer_provider(provider)

runner = Runner(
    app=adk_app,
    artifact_service=InMemoryArtifactService(),
    session_service=InMemorySessionService(),
)

app = FastAPI()


class ChatRequest(BaseModel):
    message: str
    user_id: str = "test_user"
    session_id: str = "test_session"

@app.post("/api/chat")
async def chat(request: ChatRequest):
    """Chat endpoint for the remote agent."""
    try:
        await runner.session_service.get_session(
            request.session_id, app_name=adk_app.name, user_id=request.user_id
        )
    except Exception:
        await runner.session_service.create_session(
            app_name=adk_app.name,
            user_id=request.user_id,
            session_id=request.session_id,
        )

    user_msg = genai_types.Content(
        role="user", parts=[genai_types.Part.from_text(text=request.message)]
    )

    final_text = ""
    async for event in runner.run_async(
        user_id=request.user_id, session_id=request.session_id, new_message=user_msg
    ):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    final_text += part.text + "\n"

    return {"response": final_text.strip()}

@app.get("/")
def root():
    return {"status": "ok", "service": "content_builder", "agent": adk_app.name}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)