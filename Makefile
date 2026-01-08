# ==============================================================================
# Installation & Setup
# ==============================================================================

# Install dependencies using uv package manager
install:
	@command -v uv >/dev/null 2>&1 || { echo "uv is not installed. Installing uv..."; curl -LsSf https://astral.sh/uv/0.8.13/install.sh | sh; source $HOME/.local/bin/env; }
	uv sync --dev

# ==============================================================================
# Playground Targets
# ==============================================================================

# Launch local dev playground (points to orchestrator)
# IMPORTANT: Ensure 'make run-local' is running in another terminal first!
playground:
	@echo "==============================================================================="
	@echo "| 🚀 Starting your agent playground for the Orchestrator...                   |"
	@echo "|                                                                             |"
	@echo "| ⚠️  IMPORTANT: Ensure 'make run-local' is running in another terminal!       |"
	@echo "|    The orchestrator needs the other agents to be online.                    |"
	@echo "|                                                                             |"
	@echo "| 🔍 Select 'orchestrator/app' if prompted.                                   |"
	@echo "==============================================================================="
	# Export necessary env vars for the orchestrator process running under adk web
	export GOOGLE_GENAI_USE_VERTEXAI="True"
	export GOOGLE_API_KEY="<your-api-key>"
	export RESEARCHER_AGENT_CARD_URL="http://localhost:8001/.well-known/agent.json"
	export JUDGE_AGENT_CARD_URL="http://localhost:8002/.well-known/agent.json"
	export CONTENT_BUILDER_AGENT_CARD_URL="http://localhost:8003/.well-known/agent.json"
	uv run adk web orchestrator --port 8501 --reload_agents

# ==============================================================================
# Local Development Commands
# ==============================================================================

# Run the distributed system locally without Docker
run-local:
	./run_locally.sh



# ==============================================================================
# Backend Deployment Targets
# ==============================================================================

# Deploy the agent remotely
# Usage: make deploy [IAP=true] [PORT=8080] - Set IAP=true to enable Identity-Aware Proxy, PORT to specify container port
deploy:
	@echo "Deployment for distributed agents is not yet fully automated in this Makefile."
	@echo "Please deploy each service (orchestrator, researcher, judge, content_builder) individually to Cloud Run."
	@echo "Ensure you set the *_AGENT_CARD_URL environment variables on the orchestrator service."

# Alias for 'make deploy' for backward compatibility
backend: deploy


# ==============================================================================
# Infrastructure Setup
# ==============================================================================

# Set up development environment resources using Terraform
setup-dev-env:
	PROJECT_ID=$$(gcloud config get-value project) && \
	(cd deployment/terraform/dev && terraform init && terraform apply --var-file vars/env.tfvars --var dev_project_id=$$PROJECT_ID --auto-approve)

# ==============================================================================
# Testing & Code Quality
# ==============================================================================

# Run unit and integration tests
test:
	uv run pytest tests/unit && uv run pytest tests/integration

# Run code quality checks (codespell, ruff, mypy)
lint:
	uv sync --dev --extra lint
	uv run codespell
	uv run ruff check . --diff
	uv run ruff format . --check --diff
	uv run mypy .
