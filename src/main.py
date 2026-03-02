"""
Main Entry Point

AgentCore Runtime wrapper for the AIOps Proactive Workflow.
Manages scaling, invocations, and health checks automatically.
"""

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

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv()

from src.agents import OrchestratorAgent
from src.utils.logging_config import get_logger, setup_logging
from src.workflows import AIOpsSwarm, run_proactive_workflow

setup_logging()
logger = get_logger("main")

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


@app.entrypoint
def invoke(payload: dict) -> dict:
    """
    Main entry point for AgentCore invocations.

    Supports three modes:
    - "proactive": Run the full proactive workflow (default)
    - "chat": Interactive chat with session support (A new session ID is created if not provided in payload)
    - "swarm": Run a single task through the Swarm

    Payload Examples:
        {"mode": "proactive"}
        {"mode": "chat", "message": "Why is payment-service failing?"}
        {"mode": "chat", "session_id": "abc-123", "message": "Create a ticket"}
        {"mode": "swarm", "task": "Analyze auth-service errors"}

    Returns:
        Workflow result dictionary.
    """
    logger.info(f"AgentCore invoked: {json.dumps(payload)[:200]}...")

    mode = payload.get("mode", "proactive")

    try:
        if mode == "proactive":
            return handle_proactive(payload)
        elif mode == "chat":
            return handle_chat(payload)
        elif mode == "swarm":
            return handle_swarm(payload)
        else:
            return {
                "success": False,
                "error": f"Unknown mode: {mode}",
                "supported_modes": ["proactive", "chat", "swarm"],
            }

    except Exception as e:
        logger.error(f"Invocation failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "mode": mode,
        }


def handle_proactive(payload: dict) -> dict:
    """Handle proactive workflow mode - starts in background, returns immediately."""

    task_id = app.add_async_task("proactive_workflow")
    logger.info(f"Starting proactive workflow in background (task_id: {task_id})")
    sys.stdout.flush()  # Ensure log is written to CloudWatch

    def run_in_background():
        try:
            logger.info("=== PROACTIVE WORKFLOW STARTED ===")
            sys.stdout.flush()

            result = run_proactive_workflow(destination_sink=payload.get("destination_sink", "s3"))

            logger.info("=== PROACTIVE WORKFLOW COMPLETED ===")
            logger.info(f"Workflow result: {json.dumps(result, default=str)[:1000]}")
            sys.stdout.flush()

        except Exception as e:
            logger.error("=== PROACTIVE WORKFLOW FAILED ===")
            logger.error(f"Error: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            sys.stdout.flush()

        finally:
            app.complete_async_task(task_id)
            sys.stdout.flush()

    thread = threading.Thread(target=run_in_background, daemon=True)
    thread.start()

    return {
        "success": True,
        "status": "started",
        "task_id": task_id,
        "message": "Proactive workflow started in background",
    }


def handle_chat(payload: dict) -> dict:
    """
    Handle interactive chat mode with session support.

    Uses the OrchestratorAgent for multi-turn conversations.
    When deployed on AgentCore with memory configured, conversation
    history is persisted via the AgentCore Memory service.
    """
    message = payload.get("message", "")
    session_id = payload.get("session_id")  # Single ID for both session and actor

    if not message:
        return {"success": False, "error": "Missing 'message' in payload"}

    # Use session_id for BOTH session_id and actor_id (Option B from docs)
    # This ensures consistent memory lookup across invocations
    # The client MUST provide session_id for memory to persist
    if not session_id:
        session_id = str(uuid.uuid4())
        logger.warning(
            f"No session_id provided - generated new one: {session_id}. "
            f"Memory will NOT persist unless client sends this session_id in future requests!"
        )
    else:
        logger.info(f"Using provided session_id: {session_id}")

    # Use same ID for both session and actor (per AWS docs best practice)
    actor_id = session_id
    logger.info(f"Memory lookup key: session_id={session_id}, actor_id={actor_id}")

    # Create orchestrator with session and memory enabled
    # Memory persistence is handled via AgentCore Memory service when deployed
    orchestrator = OrchestratorAgent(
        session_id=session_id,
        enable_memory=True,
        actor_id=actor_id,
    )

    # Invoke the orchestrator with the user message
    logger.info(f"Processing chat message: {message[:100]}...")

    try:
        response = orchestrator.invoke(message)

        # Extract the response text
        response_text = str(response) if response else "No response generated"

        return {
            "success": True,
            "session_id": session_id,  # Client must send this back for memory to work
            "response": response_text,
        }

    except Exception as e:
        logger.error(f"Chat invocation failed: {e}")
        return {
            "success": False,
            "session_id": session_id,
            "error": str(e),
        }


def handle_swarm(payload: dict) -> dict:
    """Handle swarm task mode."""
    task = payload.get("task", "")

    if not task:
        return {"success": False, "error": "Missing 'task' in payload"}

    logger.info(f"Running swarm task: {task[:100]}...")

    swarm = AIOpsSwarm()
    result = swarm.run(task)

    return result.to_dict()


# @app.ping
# def health() -> dict:
#     """Health check endpoint for AgentCore (GET /ping)."""
#     return {"status": "healthy", "service": "aiops-proactive-workflow"}


# Start the AgentCore server when executed directly
if __name__ == "__main__":
    logger.info("Starting AgentCore server on port 8080")
    app.run(port=8080)
