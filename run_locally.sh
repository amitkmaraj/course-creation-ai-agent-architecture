#!/bin/bash

# Kill any existing processes on these ports
echo "Stopping any existing processes on ports 8000-8003..."
lsof -ti:8000,8001,8002,8003 | xargs kill -9 2>/dev/null

# Set common environment variables for local development
export GOOGLE_CLOUD_PROJECT=$(gcloud config get-value project)
export GOOGLE_CLOUD_LOCATION="us-central1"
export GOOGLE_GENAI_USE_VERTEXAI="True" # Use Gemini API locally
export GOOGLE_API_KEY="<your-key-here>" # Use if not using Vertex AI

echo "Starting Researcher Agent on port 8001..."
cd researcher
APP_URL=http://localhost:8001 uv run uvicorn app.server:app --host 0.0.0.0 --port 8001 &
RESEARCHER_PID=$!
cd ..

echo "Starting Judge Agent on port 8002..."
cd judge
APP_URL=http://localhost:8002 uv run uvicorn app.server:app --host 0.0.0.0 --port 8002 &
JUDGE_PID=$!
cd ..

echo "Starting Content Builder Agent on port 8003..."
cd content_builder
APP_URL=http://localhost:8003 uv run uvicorn app.server:app --host 0.0.0.0 --port 8003 &
CONTENT_BUILDER_PID=$!
cd ..

# Wait a bit for them to start up
sleep 5

echo "Starting Orchestrator Agent on port 8000..."
cd orchestrator
export APP_URL=http://localhost:8000
export RESEARCHER_AGENT_CARD_URL=http://localhost:8001/.well-known/agent.json
export JUDGE_AGENT_CARD_URL=http://localhost:8002/.well-known/agent.json
export CONTENT_BUILDER_AGENT_CARD_URL=http://localhost:8003/.well-known/agent.json

uv run uvicorn app.server:app --host 0.0.0.0 --port 8000 &
ORCHESTRATOR_PID=$!
cd ..

echo "All agents started!"
echo "Orchestrator (Frontend): http://localhost:8000"
echo "Researcher: http://localhost:8001"
echo "Judge: http://localhost:8002"
echo "Content Builder: http://localhost:8003"
echo ""
echo "Press Ctrl+C to stop all agents."

# Wait for all processes
trap "kill $RESEARCHER_PID $JUDGE_PID $CONTENT_BUILDER_PID $ORCHESTRATOR_PID; exit" INT
wait
