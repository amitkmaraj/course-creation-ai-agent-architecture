# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
from typing import AsyncGenerator, Literal

import google.auth
from google.adk.agents import Agent, BaseAgent, LoopAgent, SequentialAgent
from google.adk.apps.app import App
from google.adk.events import Event, EventActions
from google.adk.agents.invocation_context import InvocationContext
from google.adk.tools import google_search
from pydantic import BaseModel, Field

# --- Configuration ---
# Set up environment variables for ADK and Google Cloud.
# In a production environment, these should be set in the environment, not hardcoded.
_, project_id = google.auth.default()
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", project_id)
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "us-central1")
# Use Vertex AI for production, Gemini API for quick testing if needed.
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "False")


# --- Data Models ---
class JudgeFeedback(BaseModel):
    """Structured feedback from the Judge agent."""

    status: Literal["pass", "fail"] = Field(
        description="Whether the research is sufficient ('pass') or needs more work ('fail')."
    )
    feedback: str = Field(
        description="Detailed feedback on what is missing or needs clarification if status is 'fail'. If 'pass', a brief confirmation."
    )


# --- Agents ---

# 1. Researcher Agent
# Responsible for gathering information using Google Search.
researcher = Agent(
    name="researcher",
    model="gemini-2.5-flash",
    description="Gathers information on a topic using Google Search.",
    instruction="""
    You are an expert researcher. Your goal is to find comprehensive and accurate information on the user's topic.
    Use the `google_search` tool to find relevant information.
    Summarize your findings clearly.
    If you receive feedback that your research is insufficient, use the feedback to refine your next search.
    """,
    tools=[google_search],
    output_key="research_findings",  # Saves output to session.state['research_findings']
)

# 2. Judge Agent
# Evaluates the research findings against the user's original request.
judge = Agent(
    name="judge",
    model="gemini-2.5-flash",
    description="Evaluates research findings for completeness and accuracy.",
    instruction="""
    You are a strict editor and fact-checker.
    Evaluate the 'research_findings' against the user's original request.
    Determine if the findings are sufficient to create a high-quality course.
    If they are good enough, output status='pass'.
    If they are missing key information, are too vague, or likely inaccurate, output status='fail' and provide specific, constructive 'feedback' on what to research next.
    """,
    output_schema=JudgeFeedback,
    output_key="judge_feedback",  # Saves structured output to session.state['judge_feedback']
    # Agents with output_schema cannot delegate, so we explicitly disable transfers to avoid warnings.
    disallow_transfer_to_parent=True,
    disallow_transfer_to_peers=True,
)


# 3. Escalation Checker (Custom Workflow Agent)
# Reads the Judge's output and decides whether to continue the loop or break it.
class EscalationChecker(BaseAgent):
    """Checks the judge's feedback and escalates (breaks the loop) if it passed."""

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        feedback = ctx.session.state.get("judge_feedback")

        # Handle feedback as a dict, as it might be deserialized as such in session state.
        if feedback and isinstance(feedback, dict) and feedback.get("status") == "pass":
            # Signal to the LoopAgent to stop iterating.
            yield Event(author=self.name, actions=EventActions(escalate=True))
        elif feedback and hasattr(feedback, "status") and feedback.status == "pass":
             # Handle case where it IS a Pydantic model (just in case)
            yield Event(author=self.name, actions=EventActions(escalate=True))
        else:
            # Continue the loop.
            yield Event(author=self.name)


escalation_checker = EscalationChecker(name="escalation_checker")

# 4. Content Builder Agent
# Takes the approved research and formats it into the final course content.
content_builder = Agent(
    name="content_builder",
    model="gemini-2.5-pro",  # Use a stronger model for final writing
    description="Transforms research findings into a structured course.",
    instruction="""
    You are an expert course creator.
    Take the approved 'research_findings' and transform them into a well-structured, engaging course module.
    Use clear headings, bullet points, and a professional tone.
    Ensure the content directly addresses the user's original request.
    """,
    # No output_key needed, its final response will be sent to the user.
)


# --- Orchestration ---

# The Research Loop: Research -> Judge -> Check -> (repeat if fail)
research_loop = LoopAgent(
    name="research_loop",
    description="Iteratively researches and judges until quality standards are met.",
    sub_agents=[researcher, judge, escalation_checker],
    max_iterations=3,  # Prevent infinite loops if research keeps failing
)

# The Main Pipeline: Research Loop -> Content Builder
root_agent = SequentialAgent(
    name="course_creation_pipeline",
    description="A pipeline that researches a topic and then builds a course from it.",
    sub_agents=[research_loop, content_builder],
)

# --- App Definition ---
app = App(root_agent=root_agent, name="app")