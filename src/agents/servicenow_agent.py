"""
ServiceNow Agent Module

Specialist agent for managing ServiceNow incidents.
"""

from ..tools.servicenow_tools import (
    ServiceNowClient,
    create_incident,
    get_incident_status,
    search_incidents,
    update_incident,
)
from .base import BaseAgent


class ServiceNowAgent(BaseAgent):
    """
    ServiceNow Specialist Agent for incident management.

    Responsibilities:
    - Create well-structured incident tickets
    - Update existing incidents with new information
    - Track incident status
    - Ensure proper categorization and priority
    - Search for tickets on ServiceNow (can be used as a knowledge base too).

    Standalone Usage:
        agent = ServiceNowAgent()

        # Simple invocation with LLM reasoning
        result = agent.invoke("Create a ticket for database connection issues")

        # Direct tool access
        ticket = agent.create_ticket(
            title="Database connection timeout",
            description="Full details...",
            priority="high"
        )
    """

    def __init__(
        self,
        model_id: str | None = None,
        region: str | None = None,
        instance: str | None = None,
        username: str | None = None,
        password: str | None = None,
    ):
        """
        Initialize the ServiceNow Agent.

        Args:
            model_id: Bedrock model ID override.
            region: AWS region override.
            instance: ServiceNow instance URL.
            username: ServiceNow username.
            password: ServiceNow password.
        """
        # Initialize the ServiceNow client for direct tool access
        self._servicenow_client = ServiceNowClient(
            instance=instance,
            username=username,
            password=password,
        )

        super().__init__(
            agent_type="servicenow",
            model_id=model_id,
            region=region,
        )

    def get_tools(self) -> list:
        """Get the ServiceNow-specific tools."""
        return [create_incident, update_incident, get_incident_status, search_incidents]
