# Distributed Agent Deployment Guide

This guide details how to deploy the multi-agent system to Google Cloud Run. Each agent will run as an independent microservice.

## Prerequisites

1.  **Google Cloud Project**: Ensure you have a GCP project and the `gcloud` CLI installed and authenticated.
    ```bash
    gcloud auth login
    gcloud config set project YOUR_PROJECT_ID
    ```
2.  **APIs Enabled**: Ensure Cloud Run and Container Registry/Artifact Registry APIs are enabled.
    ```bash
    gcloud services enable run.googleapis.com containerregistry.googleapis.com
    ```

## 1. Deploy and Configure Microservices

We will deploy the standalone agents first.

**Crucial Step:** After deploying each agent, you must update its configuration with its own public URL (`APP_URL`). This ensures the agent can correctly advertise its endpoint to other agents in the system.

### Deploy Researcher Agent

1. **Deploy:**
   ```bash
   gcloud run deploy researcher \
       --source ./researcher \
       --region us-central1 \
       --allow-unauthenticated
   ```
   *Copy the Service URL from the output (e.g., `https://researcher-xyz.a.run.app`).*

2. **Configure APP_URL:**
   ```bash
   gcloud run services update researcher \
       --region us-central1 \
       --set-env-vars APP_URL=https://researcher-795845071313.us-central1.run.app \
       --set-env-vars GOOGLE_CLOUD_PROJECT=$(gcloud config get-value project) \
       --set-env-vars GOOGLE_CLOUD_LOCATION=us-central1 \
       --set-env-vars GOOGLE_GENAI_USE_VERTEXAI=True
   ```

### Deploy Judge Agent

1. **Deploy:**
   ```bash
   gcloud run deploy judge \
       --source ./judge \
       --region us-central1 \
       --allow-unauthenticated
   ```
   *Copy the Service URL (e.g., `https://judge-xyz.a.run.app`).*

2. **Configure environment variables:**
   ```bash
   gcloud run services update judge \
       --region us-central1 \
       --set-env-vars APP_URL=https://judge-795845071313.us-central1.run.app \
       --set-env-vars GOOGLE_CLOUD_PROJECT=$(gcloud config get-value project) \
       --set-env-vars GOOGLE_CLOUD_LOCATION=us-central1 \
       --set-env-vars GOOGLE_GENAI_USE_VERTEXAI=True
   ```

### Deploy Content Builder Agent

1. **Deploy:**
   ```bash
   gcloud run deploy content-builder \
       --source ./content_builder \
       --region us-central1 \
       --allow-unauthenticated
   ```
   *Copy the Service URL (e.g., `https://content-builder-xyz.a.run.app`).*

2. **Configure environment variables:**
   ```bash
   gcloud run services update content-builder \
       --region us-central1 \
       --set-env-vars APP_URL=https://content-builder-795845071313.us-central1.run.app \
       --set-env-vars GOOGLE_CLOUD_PROJECT=$(gcloud config get-value project) \
       --set-env-vars GOOGLE_CLOUD_LOCATION=us-central1 \
       --set-env-vars GOOGLE_GENAI_USE_VERTEXAI=True
   ```

## 2. Deploy Orchestrator

Now deploy the orchestrator. You must provide it with the agent card URLs of the services you just deployed.

1. **Deploy:**
   Replace the placeholder URLs below with your actual service URLs.
   ```bash
   gcloud run deploy orchestrator \
       --source ./orchestrator \
       --region us-central1 \
       --allow-unauthenticated \
       --set-env-vars GOOGLE_CLOUD_PROJECT=$(gcloud config get-value project) \
       --set-env-vars GOOGLE_CLOUD_LOCATION=us-central1 \
       --set-env-vars GOOGLE_GENAI_USE_VERTEXAI=True \
       --set-env-vars RESEARCHER_AGENT_CARD_URL=[YOUR_RESEARCHER_URL]/.well-known/agent.json \
       --set-env-vars JUDGE_AGENT_CARD_URL=[YOUR_JUDGE_URL]/.well-known/agent.json \
       --set-env-vars CONTENT_BUILDER_AGENT_CARD_URL=[YOUR_CONTENT_BUILDER_URL]/.well-known/agent.json
   ```
   *Copy the Service URL (e.g., `https://orchestrator-xyz.a.run.app`).*

2. **Configure APP_URL:**
   ```bash
   gcloud run services update orchestrator \
       --region us-central1 \
       --set-env-vars APP_URL=[YOUR_ORCHESTRATOR_URL]
   ```

**Important**:
*   Ensure you append `/.well-known/agent.json` to each service URL when setting the environment variables for the orchestrator.

## 3. Verification

Open the Orchestrator's Service URL in your browser. You should see the Course Creation Agent frontend. Enter a topic and watch the distributed agents work together!

