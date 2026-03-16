import json
import sys
import threading
import traceback
import uuid
from pathlib import Path

from bedrock_agentcore import BedrockAgentCoreApp
from dotenv import load_dotenv
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from agents.orchestrator import OrchestratorAgent

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
    try:
        print(f"Received payload: {json.dumps(payload)}")
        orchestrator = OrchestratorAgent()
        response = orchestrator.invoke(payload.get("input", ""))
        print(f"Agent response: {response}")
        return response
    except Exception as e:
        traceback.print_exc()
        return {"error": str(e)}

if __name__ == "__main__":
    app.run(port=8080)
    
