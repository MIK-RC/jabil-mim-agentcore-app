"""
ServiceNow Agent Module

Specialist agent for managing ServiceNow incidents.
Can be used standalone or as part of the multi-agent swarm.
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

    Swarm Usage:
        # The agent's inner_agent can be used in a Swarm
        from strands.multiagent import Swarm
        swarm = Swarm(agents=[servicenow_agent.inner_agent, ...])
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
            model_id: Optional Bedrock model ID override.
            region: Optional AWS region override.
            instance: Optional ServiceNow instance URL.
            username: Optional ServiceNow username.
            password: Optional ServiceNow password.
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

    # ==========================================
    # Direct Tool Access Methods (Standalone Use)
    # ==========================================

    def create_ticket(
        self,
        title: str,
        description: str,
        priority: str = "medium",
        category: str | None = None,
        assignment_group: str | None = None,
        extra_fields: dict | None = None,
    ) -> dict:
        """
        Create a ServiceNow incident ticket directly.

        Use this for programmatic access when you don't need
        LLM reasoning, just direct ticket creation.

        Args:
            title: Short description of the incident (max 160 chars).
            description: Full description with details.
            priority: Priority level (critical, high, medium, low).
            category: Optional category override.
            assignment_group: Optional assignment group.
            extra_fields: Additional ServiceNow fields.

        Returns:
            Dictionary with created ticket details.
        """
        self._logger.info(f"Creating ticket: {title[:50]}...")

        result = self._servicenow_client.create_incident(
            short_description=title,
            description=description,
            priority=priority,
            category=category,
            assignment_group=assignment_group,
            extra=extra_fields,
        )

        success = "error" not in result
        ticket_number = result.get("number", "N/A")

        self.record_action(
            action_type="create_ticket",
            description=f"Created ticket {ticket_number}" if success else "Failed to create ticket",
            input_summary=f"Title: {title[:100]}",
            output_summary=f"Ticket: {ticket_number}"
            if success
            else result.get("error", "Unknown error"),
            success=success,
            error_message=result.get("error", "") if not success else "",
        )

        return result

    def update_ticket(
        self,
        ticket_id: str,
        work_notes: str | None = None,
        state: str | None = None,
        resolution_notes: str | None = None,
        extra_updates: dict | None = None,
    ) -> dict:
        """
        Update an existing ServiceNow ticket.

        Args:
            ticket_id: The sys_id of the ticket to update.
            work_notes: Notes about work performed.
            state: New state for the ticket.
            resolution_notes: Resolution details.
            extra_updates: Additional fields to update.

        Returns:
            Dictionary with updated ticket details.
        """
        self._logger.info(f"Updating ticket: {ticket_id}")

        updates = {}
        if work_notes:
            updates["work_notes"] = work_notes
        if state:
            updates["state"] = state
        if resolution_notes:
            updates["close_notes"] = resolution_notes
        if extra_updates:
            updates.update(extra_updates)

        if not updates:
            return {"error": "No updates provided"}

        result = self._servicenow_client.update_incident(
            sys_id=ticket_id,
            updates=updates,
        )

        success = "error" not in result

        self.record_action(
            action_type="update_ticket",
            description=f"Updated ticket {ticket_id}" if success else "Failed to update ticket",
            input_summary=f"Updates: {list(updates.keys())}",
            output_summary=f"Updated fields: {list(updates.keys())}"
            if success
            else result.get("error", "Unknown error"),
            success=success,
            error_message=result.get("error", "") if not success else "",
        )

        return result

    def get_ticket_status(self, ticket_id: str) -> dict:
        """
        Get the current status of a ticket.

        Args:
            ticket_id: The sys_id of the ticket.

        Returns:
            Dictionary with ticket status details.
        """
        self._logger.info(f"Getting status for ticket: {ticket_id}")

        result = self._servicenow_client.get_incident(ticket_id)

        if "error" not in result:
            return {
                "sys_id": result.get("sys_id"),
                "number": result.get("number"),
                "state": result.get("state"),
                "priority": result.get("priority"),
                "assigned_to": result.get("assigned_to", {}).get("display_value", "Unassigned"),
                "short_description": result.get("short_description"),
                "created_on": result.get("sys_created_on"),
                "updated_on": result.get("sys_updated_on"),
            }

        return result

    def create_ticket_from_analysis(
        self,
        service_name: str,
        analysis_report: dict,
        user_input: str = "",
        log_context: str = "",
    ) -> dict:
        """
        Create a ticket from an analysis report.

        This is a convenience method that creates a well-formatted
        ticket based on the output from the Coding Agent's analysis.

        Args:
            service_name: Name of the affected service.
            analysis_report: Dictionary from CodingAgent.full_analysis().
            user_input: Original user request (if any).
            log_context: Relevant log entries.

        Returns:
            Dictionary with created ticket details.
        """
        severity = analysis_report.get("severity", {})
        severity_level = severity.get("severity", "medium")
        patterns = analysis_report.get("patterns", {})
        suggestions = analysis_report.get("suggestions", [])

        # Build short description
        error_types = patterns.get("error_types", ["Issue"])
        short_desc = f"[{service_name}] {', '.join(error_types[:2])}"
        if len(error_types) > 2:
            short_desc += f" (+{len(error_types) - 2} more)"

        # Build full description
        description_parts = []

        if user_input:
            description_parts.append(f"## User Report\n{user_input}")

        description_parts.append(
            f"## AI Analysis Summary\n{analysis_report.get('summary', 'No summary available')}"
        )

        if suggestions:
            description_parts.append("\n## Suggested Fixes")
            for i, suggestion in enumerate(suggestions[:3], 1):
                description_parts.append(
                    f"{i}. **{suggestion.get('error_type', 'Issue')}**: "
                    f"{suggestion.get('suggestion', 'Review and fix')}"
                )

        if log_context:
            # Truncate log context to avoid overly long tickets
            truncated_logs = log_context[:2000]
            if len(log_context) > 2000:
                truncated_logs += "\n... [truncated]"
            description_parts.append(f"\n## Relevant Logs\n```\n{truncated_logs}\n```")

        description = "\n\n".join(description_parts)

        return self.create_ticket(
            title=short_desc,
            description=description,
            priority=severity_level,
            extra_fields={"category": "LLM-Assisted Resolution"},
        )

    def create_ticket_with_llm(
        self,
        issue_description: str,
        context: str = "",
    ) -> str:
        """
        Use LLM reasoning to create an appropriate ticket.

        The LLM will determine the best title, description, and
        priority based on the provided information.

        Args:
            issue_description: Description of the issue.
            context: Additional context (logs, analysis, etc.).

        Returns:
            LLM response describing the created ticket.
        """
        prompt = f"""Based on the following issue, create a ServiceNow incident ticket.

Issue Description:
{issue_description}

{f"Additional Context:{chr(10)}{context}" if context else ""}

Create a ticket with:
1. An appropriate short description (max 160 characters)
2. A detailed description including impact and suggested resolution
3. The appropriate priority level (critical, high, medium, or low)

Use the create_incident tool to create the ticket."""

        return self.invoke(prompt)

    def search_incidents(
        self,
        query: str = "",
        service_name: str | None = None,
        state: str | None = None,
        limit: int = 5,
        mode: str = "knowledge",
    ) -> list[dict]:
        """
        Search for ServiceNow incidents programmatically.

        This can be used as a knowledge base (resolved tickets)
        or to check for duplicate active tickets before creation.

        Args:
            query: Free-text search query (e.g., issue description or keywords).
            service_name: Optional service name to filter incidents (maps to category).
            state: Optional incident state to filter (overrides default per mode).
            limit: Maximum number of results to return. Defaults to 5.
            mode: 'knowledge' for resolved/closed incidents,
                'decision' for active tickets (to prevent duplicates).

        Returns:
            List of dictionaries with incident details:
            - sys_id
            - number
            - state
            - priority
            - short_description
            - assigned_to
            - created_on
            - updated_on

            Returns empty list if no matches or on error.
        """
        self._logger.info(f"Searching ServiceNow tickets (mode={mode}) with query: {query[:100]}")

        # Build ServiceNow query string
        filters = []
        if query:
            filters.append(f"short_descriptionLIKE{query}")
        if service_name:
            filters.append(f"category={service_name}")
        if state:
            filters.append(f"state={state}")
        else:
            if mode == "knowledge":
                filters.append("stateIN6,7")  # Resolved, Closed
            elif mode == "decision":
                filters.append("stateIN1,2,3,4,5")  # Active states

        sysparm_query = "^".join(filters)

        try:
            results_raw = self._servicenow_client.search_incidents(text=sysparm_query, limit=limit)

            # Standardize output
            results = []
            for r in results_raw:
                results.append(
                    {
                        "sys_id": r.get("sys_id"),
                        "number": r.get("number"),
                        "state": r.get("state"),
                        "priority": r.get("priority"),
                        "short_description": r.get("short_description"),
                        "assigned_to": r.get("assigned_to", {}).get("display_value", "Unassigned"),
                        "created_on": r.get("sys_created_on"),
                        "updated_on": r.get("sys_updated_on"),
                    }
                )

            # Record the search action
            self.record_action(
                action_type="search_tickets",
                description=f"Performed ServiceNow search ({mode})",
                input_summary=f"Query: {query[:100]}, Service: {service_name}, State: {state}, Limit: {limit}",
                output_summary=f"Found {len(results)} matching tickets",
                success=True,
            )

            return results

        except Exception as e:
            self._logger.error(f"ServiceNow search failed: {e}")
            self.record_action(
                action_type="search_tickets",
                description="ServiceNow search failed",
                input_summary=f"Query: {query[:100]}, Service: {service_name}, State: {state}, Limit: {limit}",
                output_summary=str(e),
                success=False,
                error_message=str(e),
            )
            return []
