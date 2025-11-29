import os
import json
import warnings
from typing import AsyncGenerator, Any
import google.auth
from google.adk.agents import BaseAgent, LoopAgent, SequentialAgent

# Suppress experimental warnings for A2A components
warnings.filterwarnings("ignore", message=".*\[EXPERIMENTAL\].*", category=UserWarning)

from google.adk.apps.app import App
from google.adk.events import Event, EventActions
from google.adk.agents.invocation_context import InvocationContext
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
from google.adk.agents.callback_context import CallbackContext

# --- Configuration ---
_, project_id = google.auth.default()
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", project_id)
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "us-central1")
# Default to False for local dev if not set by environment
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "False")

# --- Callbacks ---
def create_save_output_callback(key: str):
    """Creates a callback to save the agent's final response to session state."""
    def callback(callback_context: CallbackContext, **kwargs) -> None:
        ctx = callback_context
        # Find the last event from this agent that has content
        for event in reversed(ctx.session.events):
            if event.author == ctx.agent_name and event.content and event.content.parts:
                text = event.content.parts[0].text
                if text:
                    # Try to parse as JSON if it looks like it, for judge_feedback
                    if key == "judge_feedback" and text.strip().startswith("{"):
                        try:
                            ctx.state[key] = json.loads(text)
                        except json.JSONDecodeError:
                            ctx.state[key] = text
                    else:
                        ctx.state[key] = text
                    print(f"[{ctx.agent_name}] Saved output to state['{key}']")
                    return
    return callback

# --- Remote Agents ---
# These agents are running in their own containers. We connect to them via A2A.

# Default URLs assume local running on different ports if env vars are not set.
researcher_url = os.environ.get("RESEARCHER_AGENT_CARD_URL", "http://localhost:8001/.well-known/agent.json")
researcher = RemoteA2aAgent(
    name="researcher",
    agent_card=researcher_url,
    description="Gathers information on a topic using Google Search.",
    after_agent_callback=create_save_output_callback("research_findings")
)

judge_url = os.environ.get("JUDGE_AGENT_CARD_URL", "http://localhost:8002/.well-known/agent.json")
judge = RemoteA2aAgent(
    name="judge",
    agent_card=judge_url,
    description="Evaluates research findings for completeness and accuracy.",
    after_agent_callback=create_save_output_callback("judge_feedback")
)

content_builder_url = os.environ.get("CONTENT_BUILDER_AGENT_CARD_URL", "http://localhost:8003/.well-known/agent.json")
content_builder = RemoteA2aAgent(
    name="content_builder",
    agent_card=content_builder_url,
    description="Transforms research findings into a structured course."
)

# --- Local Orchestration Agents ---

class EscalationChecker(BaseAgent):
    """Checks the judge's feedback and escalates (breaks the loop) if it passed."""

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        feedback = ctx.session.state.get("judge_feedback")

        # Debug log to see what we got from the remote agent
        print(f"[EscalationChecker] Feedback received: {feedback}")

        if feedback and isinstance(feedback, dict) and feedback.get("status") == "pass":
            yield Event(author=self.name, actions=EventActions(escalate=True))
        elif isinstance(feedback, str) and '"status": "pass"' in feedback:
             yield Event(author=self.name, actions=EventActions(escalate=True))
        else:
            yield Event(author=self.name)

escalation_checker = EscalationChecker(name="escalation_checker")

# --- Orchestration ---

research_loop = LoopAgent(
    name="research_loop",
    description="Iteratively researches and judges until quality standards are met.",
    sub_agents=[researcher, judge, escalation_checker],
    max_iterations=3,
)

root_agent = SequentialAgent(
    name="course_creation_pipeline",
    description="A pipeline that researches a topic and then builds a course from it.",
    sub_agents=[research_loop, content_builder],
)

app = App(root_agent=root_agent, name="orchestrator_app")
