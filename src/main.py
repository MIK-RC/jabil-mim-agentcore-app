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
from strands.models import BedrockModel
from strands import Agent
from agents.snow_agent import ServiceNowAgent

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
model_id = "global.anthropic.claude-haiku-4-5-20251001-v1:0"
model = BedrockModel(model_id=model_id)
snow_agent = ServiceNowAgent()
agent = Agent(
    model=model, 
    tools=snow_agent.get_tools(),
    system_prompt="Act as an IT support agent using the provided tools to manage ServiceNow incidents. Use the tools to create, update, check status, search, and delete incidents as needed to assist users with their IT issues. Always provide clear and concise responses based on the tool outputs."
)

@app.ping
def health() -> dict:
    """Health check endpoint for AgentCore (GET /ping)."""
    return {"status": "healthy", "service": "aiops-proactive-workflow"}
@app.entrypoint
def invoke(payload: dict) -> dict:
    # invoke the agent with the input payload
    
    try:
        print(f"Received payload: {json.dumps(payload)}")
        response = agent(payload.get("input", ""))
        # print(f"Agent response: {json.dumps(response)}")
        # return {"response": response}
    except Exception as e:
        traceback.print_exc()
        return {"error": str(e)}

if __name__ == "__main__":
    app.run(port=8080)
    