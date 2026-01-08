import logging
import os
import json
import warnings
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

# Suppress experimental warnings for A2A components
warnings.filterwarnings("ignore", message=r".*\[EXPERIMENTAL\].*", category=UserWarning)

# Suppress runner app name mismatch warning
logging.getLogger("google_adk.google.adk.runners").setLevel(logging.ERROR)
logging.getLogger("google.adk.runners").setLevel(logging.ERROR)

# Suppress Google Auth warnings
warnings.filterwarnings("ignore", message=".*Your application has authenticated using end user credentials.*")

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class SimpleChatRequest(BaseModel):
    message: str
    user_id: str = "test_user"
    session_id: str = "test_session"

@app.post("/api/chat_stream")
async def chat_stream(request: SimpleChatRequest):
    """Streaming chat endpoint."""
    try:
        session = await runner.session_service.get_session(
            session_id=request.session_id, app_name=adk_app.name, user_id=request.user_id
        )
    except Exception:
        session = None
    if not session:
        session = await runner.session_service.create_session(
            app_name=adk_app.name,
            user_id=request.user_id,
            session_id=request.session_id,
        )

    user_msg = genai_types.Content(
        role="user", parts=[genai_types.Part.from_text(text=request.message)]
    )

    async def event_generator():
        final_text = ""
        async for event in runner.run_async(
            user_id=request.user_id, session_id=session.id, new_message=user_msg
        ):
            # Send progress updates based on which agent is active
            if event.author == "researcher":
                 yield json.dumps({"type": "progress", "text": "🔍 Researcher is gathering information..."}) + "\n"
            elif event.author == "judge":
                 yield json.dumps({"type": "progress", "text": "⚖️ Judge is evaluating findings..."}) + "\n"
            elif event.author == "content_builder":
                 yield json.dumps({"type": "progress", "text": "✍️ Content Builder is writing the course..."}) + "\n"

            # Accumulate final text
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        final_text += part.text

        # Send final result
        yield json.dumps({"type": "result", "text": final_text.strip()}) + "\n"

    return StreamingResponse(event_generator(), media_type="application/x-ndjson")

@app.post("/feedback")
def collect_feedback(feedback: Feedback) -> dict[str, str]:
    logger.info(f"Feedback received: {feedback.model_dump()}")
    return {"status": "success"}

# Mount frontend from the copied location
frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.exists(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)