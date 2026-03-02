"""
AgentCore Memory Session Manager Module

Provides a factory function to create AgentCore Memory session managers
for use with Strands agents. Wraps the bedrock_agentcore SDK's built-in
Strands integration.
"""

import os
import traceback
import uuid as uuid_mod
from typing import Any

# Import AgentCore Memory session manager
from bedrock_agentcore.memory.integrations.strands.config import (
    AgentCoreMemoryConfig,
)
from bedrock_agentcore.memory.integrations.strands.session_manager import (
    AgentCoreMemorySessionManager,
)
from strands.session import FileSessionManager

from ..utils.config_loader import load_settings
from ..utils.logging_config import get_logger

logger = get_logger("memory.agentcore")


def is_running_in_agentcore() -> bool:
    """
    Detect if the application is running in AWS AgentCore environment.

    Returns:
        True if running in AgentCore, False otherwise.
    """
    # AgentCore sets specific environment variables when running
    # Check for common indicators of AgentCore/ECS environment
    return bool(
        os.environ.get("AWS_EXECUTION_ENV")
        or os.environ.get("ECS_CONTAINER_METADATA_URI")
        or os.environ.get("AGENTCORE_MEMORY_ID")
    )


def create_agentcore_session_manager(
    session_id: str,
    actor_id: str | None = None,
    memory_id: str | None = None,
    region: str | None = None,
) -> Any:
    """
    Create a session manager for AgentCore Memory integration.

    When running in AgentCore, returns an AgentCoreMemorySessionManager
    that persists conversation history to the AgentCore Memory service.

    When running locally (or if AgentCore Memory is not configured),
    falls back to FileSessionManager for local development.

    Args:
        session_id: Unique identifier for the session.
        actor_id: Unique identifier for the user/actor. Defaults to "user".
        memory_id: AgentCore Memory ID. Can be set via AGENTCORE_MEMORY_ID env var.
        region: AWS region. Defaults to config or us-east-1.

    Returns:
        A session manager instance (AgentCoreMemorySessionManager or FileSessionManager).

    Usage:
        # In AgentCore environment with memory configured
        manager = create_agentcore_session_manager(
            session_id="user-123",
            actor_id="user-123",
        )

        # For local development (falls back to file storage)
        manager = create_agentcore_session_manager(session_id="test-session")
    """
    settings = load_settings()
    session_config = settings.get("session", {})
    aws_config = settings.get("aws", {})

    # Resolve memory_id from parameter, env var, or config
    resolved_memory_id = (
        memory_id or os.environ.get("AGENTCORE_MEMORY_ID") or session_config.get("memory_id")
    )

    # Resolve region
    resolved_region = region or aws_config.get("region", "us-east-1")

    # Resolve actor_id (generate unique ID if not specified)
    if not actor_id:
        resolved_actor_id = f"user-{uuid_mod.uuid4().hex[:12]}"
        logger.info(f"Generated actor_id: {resolved_actor_id}")
    else:
        resolved_actor_id = actor_id

    # Check if we should use AgentCore Memory
    use_agentcore = session_config.get("backend", "auto") == "agentcore" or (
        session_config.get("backend", "auto") == "auto" and is_running_in_agentcore()
    )

    if use_agentcore and resolved_memory_id:
        try:
            config = AgentCoreMemoryConfig(
                memory_id=resolved_memory_id,
                session_id=session_id,
                actor_id=resolved_actor_id,
            )

            logger.info(
                f"Creating AgentCore Memory session manager: "
                f"memory_id={resolved_memory_id}, session_id={session_id}"
            )

            return AgentCoreMemorySessionManager(
                agentcore_memory_config=config,
                region_name=resolved_region,
            )

        except ImportError as e:
            logger.warning(f"AgentCore Memory SDK not available, falling back to file storage: {e}")
        except Exception as e:
            # Log the full error for debugging in production

            logger.error(
                f"Failed to create AgentCore Memory session manager: {e}\n"
                f"Traceback: {traceback.format_exc()}\n"
                f"Falling back to file storage (WARNING: will not persist across invocations!)"
            )

    # Fallback to file-based session manager for local development
    storage_dir = session_config.get("local_storage_dir", "./sessions")
    logger.info(f"Creating file session manager: {storage_dir}/{session_id}")

    return FileSessionManager(
        session_id=session_id,
        storage_dir=storage_dir,
    )
