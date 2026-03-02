"""
Base Agent Module

Provides the BaseAgent class that all specialized agents inherit from.
Contains shared functionality for initialization, logging, and action tracking.
"""

import time
import uuid
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field
from strands import Agent
from strands.models.bedrock import BedrockModel

from ..utils.config_loader import AgentConfig, get_agent_config, load_settings
from ..utils.logging_config import get_logger


def _utc_now_iso() -> str:
    """Get current UTC time as ISO string."""
    return datetime.now(UTC).isoformat()


class AgentAction(BaseModel):
    """Record of a single agent action."""

    timestamp: str = Field(default_factory=_utc_now_iso)
    action_type: str
    description: str
    input_summary: str = ""
    output_summary: str = ""
    success: bool = True
    error_message: str = ""
    duration_ms: int = 0


class AgentState(BaseModel):
    """State tracking for an agent instance."""

    agent_id: str
    agent_name: str
    created_at: str = Field(default_factory=_utc_now_iso)
    last_activity: str = Field(default_factory=_utc_now_iso)
    action_history: list[AgentAction] = Field(default_factory=list)
    total_invocations: int = 0
    successful_invocations: int = 0
    failed_invocations: int = 0


class BaseAgent(ABC):
    """
    Base class for all AIOps agents.

    Provides common functionality:
    - Configuration loading from YAML
    - Bedrock model initialization
    - Action history tracking
    - Logging integration
    - Standalone and swarm operation modes

    Usage:
        class MyAgent(BaseAgent):
            def __init__(self):
                super().__init__(agent_type="my_agent")

            def get_tools(self):
                return [my_tool_1, my_tool_2]

            def invoke(self, message: str) -> str:
                return self._agent(message)
    """

    def __init__(
        self,
        agent_type: str,
        custom_config: AgentConfig | None = None,
        model_id: str | None = None,
        region: str | None = None,
        session_manager: Any | None = None,
    ):
        """
        Initialize the base agent.

        Args:
            agent_type: Type of agent (e.g., "orchestrator", "datadog").
                       Used to load configuration from agents.yaml.
            custom_config: Optional custom AgentConfig to override YAML config.
            model_id: Optional model ID to override config.
            region: Optional AWS region to override config.
            session_manager: Optional session manager for conversation persistence.
        """
        self._agent_type = agent_type
        self._agent_id = f"{agent_type}-{uuid.uuid4().hex[:8]}"

        # Load configuration
        self._settings = load_settings()

        if custom_config:
            self._config = custom_config
        else:
            agent_cfg = get_agent_config(agent_type)
            self._config = AgentConfig(**agent_cfg)

        # Initialize logger
        self._logger = get_logger(
            f"agents.{agent_type}",
            agent_id=self._agent_id,
        )

        # Initialize state
        self._state = AgentState(
            agent_id=self._agent_id,
            agent_name=self._config.name,
        )

        # Initialize Bedrock model
        effective_region = region or self._settings.get("aws", {}).get("region", "us-east-1")
        effective_model_id = model_id or self._config.model_id

        self._model = BedrockModel(
            model_id=effective_model_id,
            region_name=effective_region,
        )

        # Initialize the Strands agent
        self._agent = self._create_agent(session_manager)

        self._logger.info(f"Initialized {self._config.name} with model {effective_model_id}")

    def _create_agent(self, session_manager: Any | None = None) -> Agent:
        """
        Create the Strands Agent instance.

        Args:
            session_manager: Optional session manager for persistence.

        Returns:
            Configured Agent instance.
        """
        agent_kwargs = {
            "model": self._model,
            "system_prompt": self._config.system_prompt,
            "tools": self.get_tools(),
            "name": self._config.name,
            "description": self._config.description,
        }

        if session_manager:
            agent_kwargs["session_manager"] = session_manager

        return Agent(**agent_kwargs)

    @property
    def agent_id(self) -> str:
        """Get the unique agent ID."""
        return self._agent_id

    @property
    def agent_name(self) -> str:
        """Get the agent name from config."""
        return self._config.name

    @property
    def description(self) -> str:
        """Get the agent description."""
        return self._config.description

    @property
    def state(self) -> AgentState:
        """Get the current agent state."""
        return self._state

    @property
    def action_history(self) -> list[AgentAction]:
        """Get the action history."""
        return self._state.action_history

    @property
    def inner_agent(self) -> Agent:
        """
        Get the underlying Strands Agent instance.

        Useful for advanced operations or swarm integration.
        """
        return self._agent

    @abstractmethod
    def get_tools(self) -> list:
        """
        Get the list of tools available to this agent.

        Must be implemented by subclasses.

        Returns:
            List of tool functions decorated with @tool.
        """
        pass

    def record_action(
        self,
        action_type: str,
        description: str,
        input_summary: str = "",
        output_summary: str = "",
        success: bool = True,
        error_message: str = "",
        duration_ms: int = 0,
    ) -> None:
        """
        Record an action in the agent's history.

        Args:
            action_type: Type of action (e.g., "invoke", "tool_call").
            description: Human-readable description of the action.
            input_summary: Summary of the input.
            output_summary: Summary of the output.
            success: Whether the action succeeded.
            error_message: Error message if action failed.
            duration_ms: Duration of the action in milliseconds.
        """
        action = AgentAction(
            action_type=action_type,
            description=description,
            input_summary=input_summary[:500] if input_summary else "",
            output_summary=output_summary[:500] if output_summary else "",
            success=success,
            error_message=error_message,
            duration_ms=duration_ms,
        )

        self._state.action_history.append(action)
        self._state.last_activity = datetime.now(UTC).isoformat()

        if success:
            self._state.successful_invocations += 1
        else:
            self._state.failed_invocations += 1

        self._state.total_invocations += 1

    def invoke(self, message: str, **kwargs) -> str:
        """
        Invoke the agent with a message.

        This is the main entry point for interacting with the agent.

        Args:
            message: The user message or task description.
            **kwargs: Additional arguments passed to the agent.

        Returns:
            The agent's response as a string.
        """
        start_time = time.time()

        self._logger.info(f"Invoking agent with message: {message[:100]}...")

        try:
            result = self._agent(message, **kwargs)
            response = str(result)
            duration_ms = int((time.time() - start_time) * 1000)

            self.record_action(
                action_type="invoke",
                description="Processed user request",
                input_summary=message,
                output_summary=response,
                success=True,
                duration_ms=duration_ms,
            )

            self._logger.info(f"Agent response generated in {duration_ms}ms")
            return response

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            error_msg = str(e)

            self.record_action(
                action_type="invoke",
                description="Failed to process request",
                input_summary=message,
                error_message=error_msg,
                success=False,
                duration_ms=duration_ms,
            )

            self._logger.error(f"Agent invocation failed: {error_msg}")
            raise

    async def ainvoke(self, message: str, **kwargs) -> str:
        """
        Asynchronously invoke the agent with a message.

        Args:
            message: The user message or task description.
            **kwargs: Additional arguments passed to the agent.

        Returns:
            The agent's response as a string.
        """
        # Strands SDK supports async via the agent's async methods

        start_time = time.time()

        self._logger.info(f"Async invoking agent with message: {message[:100]}...")

        try:
            # Use the agent's async streaming or invoke method
            result = self._agent.stream_async(message, **kwargs)
            response = ""
            async for event in result:
                if hasattr(event, "data"):
                    response += str(event.data)

            duration_ms = int((time.time() - start_time) * 1000)

            self.record_action(
                action_type="async_invoke",
                description="Processed user request (async)",
                input_summary=message,
                output_summary=response,
                success=True,
                duration_ms=duration_ms,
            )

            return response

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)

            self.record_action(
                action_type="async_invoke",
                description="Failed to process request (async)",
                input_summary=message,
                error_message=str(e),
                success=False,
                duration_ms=duration_ms,
            )

            self._logger.error(f"Async agent invocation failed: {e}")
            raise

    def get_action_summary(self) -> str:
        """
        Get a natural language summary of the agent's actions.

        Returns:
            Formatted string summarizing all recorded actions.
        """
        if not self._state.action_history:
            return f"{self.agent_name} has not performed any actions yet."

        lines = [
            f"## {self.agent_name} Action Summary",
            f"Total invocations: {self._state.total_invocations}",
            f"Successful: {self._state.successful_invocations}",
            f"Failed: {self._state.failed_invocations}",
            "",
            "### Action History:",
        ]

        for i, action in enumerate(self._state.action_history, 1):
            status = "✓" if action.success else "✗"
            lines.append(f"{i}. [{status}] {action.action_type}: {action.description}")
            if action.error_message:
                lines.append(f"   Error: {action.error_message}")

        return "\n".join(lines)

    def reset_state(self) -> None:
        """Reset the agent's state and action history."""
        self._state = AgentState(
            agent_id=self._agent_id,
            agent_name=self._config.name,
        )
        self._logger.info("Agent state reset")

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(id={self._agent_id}, name={self.agent_name})"
