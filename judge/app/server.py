import logging
import os
import warnings
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

# Suppress experimental warnings for A2A components
warnings.filterwarnings("ignore", message=".*\[EXPERIMENTAL\].*", category=UserWarning)

# Suppress runner app name mismatch warning
logging.getLogger("google.adk.runners").setLevel(logging.ERROR)

from a2a.server.apps import A2AFastAPIApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard
from fastapi import FastAPI
from google.adk.a2a.executor.a2a_agent_executor import A2aAgentExecutor
from google.adk.a2a.utils.agent_card_builder import AgentCardBuilder
from google.adk.artifacts.in_memory_artifact_service import InMemoryArtifactService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from app.agent import app as adk_app

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

runner = Runner(
    app=adk_app,
    artifact_service=InMemoryArtifactService(),
    session_service=InMemorySessionService(),
)

request_handler = DefaultRequestHandler(
    agent_executor=A2aAgentExecutor(runner=runner), task_store=InMemoryTaskStore()
)

# Simplified paths for A2A
A2A_RPC_PATH = "/rpc"

async def build_dynamic_agent_card() -> AgentCard:
    agent_card_builder = AgentCardBuilder(
        agent=adk_app.root_agent,
        capabilities=AgentCapabilities(streaming=True),
        rpc_url=f"{os.getenv('APP_URL', 'http://0.0.0.0:8000')}{A2A_RPC_PATH}",
        agent_version=os.getenv("AGENT_VERSION", "0.1.0"),
    )
    return await agent_card_builder.build()

@asynccontextmanager
async def lifespan(app_instance: FastAPI) -> AsyncIterator[None]:
    agent_card = await build_dynamic_agent_card()
    a2a_app = A2AFastAPIApplication(agent_card=agent_card, http_handler=request_handler)
    
    # Simplified paths
    agent_card_url = "/.well-known/agent.json"
    extended_agent_card_url = "/extended-agent-card.json"
    rpc_url = A2A_RPC_PATH
    
    logger.info(f"Registering A2A routes: card={agent_card_url}, rpc={rpc_url}")

    a2a_app.add_routes_to_app(
        app_instance,
        agent_card_url=agent_card_url,
        rpc_url=rpc_url,
        extended_agent_card_url=extended_agent_card_url,
    )
    yield

app = FastAPI(lifespan=lifespan)

@app.get("/")
def root():
    return {"status": "ok", "service": "judge", "agent": adk_app.name}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)