"""
Orchestrator Agent Module

Central coordinator agent that manages all specialist agents and user interactions.
Maintains conversation history and generates comprehensive reports.
"""

from ..utils.logging_config import get_logger
from .base import BaseAgent
from .servicenow_agent import ServiceNowAgent

# Module-level logger for use before instance is initialized
_module_logger = get_logger("agents.orchestrator")


class OrchestratorAgent(BaseAgent):
    """
    Orchestrator Agent - Central coordinator for the AIOps system.

    Responsibilities:
    - Coordinate specialist agents (ServiceNow)

    The orchestrator can operate in two modes:
    1. Standalone: Direct user interaction with manual agent coordination
    2. Swarm: Automated multi-agent coordination via Strands Swarm

    Standalone Usage:
        orchestrator = OrchestratorAgent()

        # User interaction
        result = orchestrator.invoke("Analyze errors in the payment service")

        # Get report of all actions
        report = orchestrator.generate_report()
    """

    def __init__(
        self,
        model_id: str | None = None,
        region: str | None = None,
    ):
        """
        Initialize the Orchestrator Agent.

        Args:
            model_id: Optional Bedrock model ID override.
            region: Optional AWS region override.
        """

        # Initialize specialist agents (lazy loaded)
        self._servicenow_agent: ServiceNowAgent | None = None

        # Store all agent reports for final summary
        self._agent_reports: list[dict] = []

        super().__init__(
            agent_type="orchestrator",
            model_id=model_id,
            region=region,
        )

    def get_tools(self) -> list:
        """
        Get the orchestrator's tools.

        The orchestrator primarily uses specialist agents rather than
        direct tools, but may have utility tools for reporting.
        """
        # Import here to avoid circular dependency
        from ..tools.servicenow_tools import create_incident, search_incidents

        # The orchestrator can access high-level tools from all agents
        return [create_incident, search_incidents]

    # ==========================================
    # Specialist Agent Access
    # ==========================================

    @property
    def servicenow_agent(self) -> ServiceNowAgent:
        """Get or create the ServiceNow agent."""
        if self._servicenow_agent is None:
            self._servicenow_agent = ServiceNowAgent()
        return self._servicenow_agent

    def get_all_agent_actions(self) -> list[dict]:
        """
        Get actions from all agents in the system.

        Returns:
            List of all agent actions with agent attribution.
        """
        all_actions = []

        # Orchestrator actions
        for action in self.action_history:
            all_actions.append(
                {
                    "agent": "Orchestrator",
                    **action.model_dump(),
                }
            )

        # ServiceNow agent actions
        if self._servicenow_agent:
            for action in self._servicenow_agent.action_history:
                all_actions.append(
                    {
                        "agent": "ServiceNow",
                        **action.model_dump(),
                    }
                )

        # Sort by timestamp
        all_actions.sort(key=lambda x: x.get("timestamp", ""))

        return all_actions

    def reset_all_agents(self) -> None:
        """Reset state for all agents."""
        self.reset_state()
        self._agent_reports = []

        if self._servicenow_agent:
            self._servicenow_agent.reset_state()

        self._logger.info("All agent states reset")
