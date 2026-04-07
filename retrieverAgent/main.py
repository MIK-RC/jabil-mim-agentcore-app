import json
import os
import sys
import traceback
from pathlib import Path

from bedrock_agentcore import BedrockAgentCoreApp
from dotenv import load_dotenv
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from myAgent.sharepoint_agent import SharePointAgent

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv()


# Initialize AgentCore app with CORS middleware
app = BedrockAgentCoreApp(
    middleware=[
        Middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=False,
            allow_methods=["GET", "POST"],
            allow_headers=["*"],
        )
    ]
)


@app.ping
def health() -> dict:
    """Health check endpoint for AgentCore (GET /ping)."""
    return {"status": "healthy", "service": "aiops-proactive-workflow"}


@app.entrypoint
def invoke(payload: dict) -> dict:
    """
    This is a POST request method and serves as the entrypoint of the deployed/running AgentCore application
    The method is attached to a single orchestrator agent which routes our request to an appropriate sub-agent or
    handles the response themselves:
    Args,
        input: str - The input that is to be processed by the orchestrating agent.
    Returns,
        response: dict - A dictionary object with the following keys and values:
                        1) agent_output: str - Culmination of the agentic orchestration.
                        2) error: str - Error message (if any).
    """
    try:
        print(f"Received payload: {json.dumps(payload)}")
        
        # Get OpenSearch host from environment variable
        opensearch_host = os.environ.get("OPENSEARCH_HOST")
        if not opensearch_host:
            raise ValueError("OPENSEARCH_HOST environment variable not set. Please set it to your OpenSearch endpoint.")
        
        orchestrator = SharePointAgent(opensearch_host=opensearch_host)
        response = orchestrator.invoke(payload.get("input", ""))
        print(f"Agent response: {response}")
        response = {"agent_output": response, "error": "None"}
        return response
    except Exception as e:
        traceback.print_exc()
        return {"error": str(e)}


if __name__ == "__main__":
    app.run(port=8080)
