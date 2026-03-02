"""
ServiceNow Tools Module

Tools for interacting with the ServiceNow API to manage incidents.
These tools can be used standalone or as part of the ServiceNow Agent.
"""

import os

import requests
from strands import tool

from ..utils.config_loader import load_tools_config
from ..utils.logging_config import get_logger

logger = get_logger("tools.servicenow")


class ServiceNowClient:
    """
    ServiceNow API client for incident management.

    Can be used standalone or through the tool functions.

    Usage:
        # Standalone usage
        client = ServiceNowClient()
        ticket = client.create_incident(
            short_description="Database connection timeout",
            description="Full details here..."
        )

        # With custom credentials
        client = ServiceNowClient(
            instance="mycompany.service-now.com",
            username="api_user",
            password="api_password"
        )
    """

    def __init__(
        self,
        instance: str | None = None,
        username: str | None = None,
        password: str | None = None,
    ):
        """
        Initialize the ServiceNow client.

        Args:
            instance: ServiceNow instance URL (e.g., "mycompany.service-now.com").
                     Defaults to SERVICENOW_INSTANCE env var.
            username: ServiceNow username. Defaults to SERVICENOW_USER env var.
            password: ServiceNow password. Defaults to SERVICENOW_PASS env var.
        """
        self._config = load_tools_config().get("servicenow", {})

        self._instance = instance or os.environ.get("SERVICENOW_INSTANCE")
        self._username = username or os.environ.get("SERVICENOW_USER", "")
        self._password = password or os.environ.get("SERVICENOW_PASS", "")

        if not self._instance:
            logger.warning("ServiceNow instance not configured")

        self._timeout = self._config.get("request", {}).get("timeout_seconds", 30)

    @property
    def base_url(self) -> str:
        """Get the base URL for the ServiceNow instance."""
        if not self._instance:
            return ""
        # Handle both full URL and instance name
        if self._instance.startswith("http"):
            return self._instance.rstrip("/")
        return f"https://{self._instance}"

    @property
    def auth(self) -> tuple[str, str]:
        """Get the authentication tuple."""
        return (self._username, self._password)

    @property
    def headers(self) -> dict[str, str]:
        """Get the request headers."""
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _get_priority_values(self, priority: str) -> tuple[str, str]:
        """
        Get impact and urgency values for a priority level.

        Args:
            priority: Priority level (critical, high, medium, low)

        Returns:
            Tuple of (impact, urgency) values
        """
        mapping = self._config.get("priority_mapping", {})
        defaults = self._config.get("defaults", {})

        if priority.lower() in mapping:
            priority_config = mapping[priority.lower()]
            return (
                priority_config.get("impact", defaults.get("impact", "3")),
                priority_config.get("urgency", defaults.get("urgency", "3")),
            )

        return (defaults.get("impact", "3"), defaults.get("urgency", "3"))

    def create_incident(
        self,
        short_description: str,
        description: str,
        priority: str = "medium",
        category: str | None = None,
        assignment_group: str | None = None,
        extra: dict | None = None,
    ) -> dict:
        """
        Create a new incident in ServiceNow.

        Args:
            short_description: Brief description of the incident (max 160 chars).
            description: Full description with details.
            priority: Priority level (critical, high, medium, low).
            category: Incident category. Defaults to config default.
            assignment_group: Group to assign the ticket to.
            extra: Additional fields to include in the ticket.

        Returns:
            Dict containing the created incident details including sys_id and number.
        """
        if not self.base_url:
            logger.error("ServiceNow instance not configured")
            return {"error": "ServiceNow instance not configured"}

        defaults = self._config.get("defaults", {})
        endpoint = self._config.get("endpoints", {}).get("incidents", "/api/now/table/incident")
        url = f"{self.base_url}{endpoint}"

        # Get impact and urgency from priority
        impact, urgency = self._get_priority_values(priority)

        payload = {
            "short_description": short_description[:160],  # Enforce max length
            "description": description,
            "impact": impact,
            "urgency": urgency,
            "category": category or defaults.get("category", "LLM-Assisted Resolution"),
        }

        # Add assignment group if specified
        if assignment_group or defaults.get("assignment_group"):
            payload["assignment_group"] = assignment_group or defaults.get("assignment_group")

        # Merge extra fields
        if extra:
            payload.update(extra)

        logger.info(f"Creating ServiceNow incident: {short_description[:50]}...")

        try:
            response = requests.post(
                url,
                auth=self.auth,
                headers=self.headers,
                json=payload,
                timeout=self._timeout,
            )
            response.raise_for_status()

            result = response.json().get("result", {})

            logger.info(
                f"Created incident: {result.get('number', 'N/A')} "
                f"(sys_id: {result.get('sys_id', 'N/A')})"
            )

            return result

        except requests.exceptions.Timeout:
            logger.error("ServiceNow API request timed out")
            return {"error": "Request timed out"}
        except requests.exceptions.RequestException as e:
            logger.error(f"ServiceNow API request failed: {e}")
            return {"error": str(e)}

    def update_incident(
        self,
        sys_id: str,
        updates: dict,
    ) -> dict:
        """
        Update an existing incident.

        Args:
            sys_id: The sys_id of the incident to update.
            updates: Dictionary of fields to update.

        Returns:
            Dict containing the updated incident details.
        """
        if not self.base_url:
            logger.error("ServiceNow instance not configured")
            return {"error": "ServiceNow instance not configured"}

        endpoint = self._config.get("endpoints", {}).get("incidents", "/api/now/table/incident")
        url = f"{self.base_url}{endpoint}/{sys_id}"

        logger.info(f"Updating incident: {sys_id}")

        try:
            response = requests.patch(
                url,
                auth=self.auth,
                headers=self.headers,
                json=updates,
                timeout=self._timeout,
            )
            response.raise_for_status()

            result = response.json().get("result", {})
            logger.info(f"Updated incident: {result.get('number', sys_id)}")

            return result

        except requests.exceptions.RequestException as e:
            logger.error(f"ServiceNow update failed: {e}")
            return {"error": str(e)}

    def get_incident(self, sys_id: str) -> dict:
        """
        Get details of an existing incident.

        Args:
            sys_id: The sys_id of the incident.

        Returns:
            Dict containing the incident details.
        """
        if not self.base_url:
            logger.error("ServiceNow instance not configured")
            return {"error": "ServiceNow instance not configured"}

        endpoint = self._config.get("endpoints", {}).get("incidents", "/api/now/table/incident")
        url = f"{self.base_url}{endpoint}/{sys_id}"

        try:
            response = requests.get(
                url,
                auth=self.auth,
                headers=self.headers,
                timeout=self._timeout,
            )
            response.raise_for_status()

            return response.json().get("result", {})

        except requests.exceptions.RequestException as e:
            logger.error(f"ServiceNow get failed: {e}")
            return {"error": str(e)}

    def search_incidents(
        self,
        text: str | None = None,
        states: list[str] | None = None,
        limit: int | None = None,
        mode: str = "decision",
        raw_query: str | None = None,
    ) -> list[dict]:
        """
        Search incidents in ServiceNow.

        Supports structured search with optional OR-based text matching,
        state filtering, ordering by most recent update, and result limiting.

        Args:
            text: Free-text to search across configured fields.
            states: List of incident states to filter on (display values).
            limit: Max number of results to return.
            mode: "decision" (deduplication) or "knowledge" (resolution lookup).
            raw_query: Optional raw sysparm_query string (takes precedence).

        Returns:
            List of incident records (shape depends on mode).
        """
        if not self.base_url:
            logger.error("ServiceNow instance not configured")
            return [{"error": "ServiceNow instance not configured"}]

        search_cfg = self._config.get("search", {})
        endpoint = self._config.get("endpoints", {}).get("incidents", "/api/now/table/incident")

        url = f"{self.base_url}{endpoint}"

        limit = limit or search_cfg.get("default_limit", 5)
        order = search_cfg.get("default_order", "ORDERBYDESCsys_updated_on")

        # Determine default states by mode if not provided
        if not states:
            states = search_cfg.get("default_states", {}).get(mode, [])

        query_parts: list[str] = []

        # Raw query takes precedence
        if raw_query:
            query = raw_query
        else:
            # Text search (OR across fields)
            if text:
                fields = search_cfg.get(
                    "searchable_fields",
                    ["short_description", "description", "close_notes"],
                )
                text_query = "^OR".join(f"{field}LIKE{text}" for field in fields)
                query_parts.append(f"({text_query})")

            # State filters
            if states:
                state_query = "^OR".join(f"state={state}" for state in states)
                query_parts.append(f"({state_query})")

            query = "^".join(query_parts) if query_parts else ""

        # Always apply ordering
        if query:
            query = f"{query}^{order}"
        else:
            query = order

        params = {
            "sysparm_query": query,
            "sysparm_limit": limit,
        }

        logger.info(f"Searching ServiceNow incidents (mode={mode}, limit={limit})")

        try:
            response = requests.get(
                url,
                auth=self.auth,
                headers=self.headers,
                params=params,
                timeout=self._timeout,
            )
            response.raise_for_status()

            results = response.json().get("result", [])

            # Shape results by mode
            if mode == "knowledge":
                return [
                    {
                        "sys_id": r.get("sys_id"),
                        "number": r.get("number"),
                        "state": r.get("state"),
                        "priority": r.get("priority"),
                        "short_description": r.get("short_description"),
                        "description": r.get("description"),
                        "close_notes": r.get("close_notes"),
                        "updated_on": r.get("sys_updated_on"),
                    }
                    for r in results
                ]

            # decision mode (default)
            return [
                {
                    "sys_id": r.get("sys_id"),
                    "number": r.get("number"),
                    "state": r.get("state"),
                    "priority": r.get("priority"),
                    "short_description": r.get("short_description"),
                    "updated_on": r.get("sys_updated_on"),
                }
                for r in results
            ]

        except requests.exceptions.RequestException as e:
            logger.error(f"ServiceNow search failed: {e}")
            return [{"error": str(e)}]


# Create a default client instance for tool functions
_default_client: ServiceNowClient | None = None


def _get_client() -> ServiceNowClient:
    """Get or create the default ServiceNow client."""
    global _default_client
    if _default_client is None:
        _default_client = ServiceNowClient()
    return _default_client


@tool
def create_incident(
    short_description: str,
    description: str,
    priority: str = "medium",
    category: str = "",
) -> dict:
    """
    Create a new incident ticket in ServiceNow.

    This tool creates an incident in ServiceNow's ITSM system with the provided
    details. Use it when an issue has been identified that requires tracking.

    Args:
        short_description: Brief summary of the incident (max 160 characters).
                          Should be clear and actionable.
                          Example: "[payment-api] Database connection timeouts"
        description: Full description of the incident including:
                    - What happened
                    - When it happened
                    - Impact assessment
                    - Suggested resolution
                    - Related log entries or evidence
        priority: Priority level of the incident.
                 Options: "critical", "high", "medium", "low"
                 Defaults to "medium".
        category: Optional category for the incident.
                 Defaults to "LLM-Assisted Resolution" if not specified.

    Returns:
        Dictionary containing:
        - sys_id: Unique identifier for the incident
        - number: Human-readable incident number (e.g., "INC0012345")
        - state: Current state of the incident
        - Or error details if creation failed

    Example:
        result = create_incident(
            short_description="[user-service] Authentication failures spike",
            description="Multiple authentication failures detected...",
            priority="high"
        )
    """
    client = _get_client()
    return client.create_incident(
        short_description=short_description,
        description=description,
        priority=priority,
        category=category if category else None,
    )


@tool
def update_incident(
    incident_id: str,
    work_notes: str = "",
    state: str = "",
    resolution_notes: str = "",
) -> dict:
    """
    Update an existing incident in ServiceNow.

    This tool updates an incident with new information such as work notes,
    state changes, or resolution details.

    Args:
        incident_id: The sys_id of the incident to update.
        work_notes: Notes about work performed on the incident.
                   These are visible to the assigned team.
        state: New state for the incident.
               Common values: "In Progress", "On Hold", "Resolved", "Closed"
        resolution_notes: Notes about how the incident was resolved.
                         Required when setting state to "Resolved".

    Returns:
        Dictionary containing the updated incident details or error information.

    Example:
        result = update_incident(
            incident_id="abc123...",
            work_notes="Implemented connection pooling fix",
            state="Resolved",
            resolution_notes="Deployed fix v1.2.3 to production"
        )
    """
    client = _get_client()

    updates = {}
    if work_notes:
        updates["work_notes"] = work_notes
    if state:
        updates["state"] = state
    if resolution_notes:
        updates["close_notes"] = resolution_notes

    if not updates:
        return {"error": "No updates provided"}

    return client.update_incident(sys_id=incident_id, updates=updates)


@tool
def get_incident_status(incident_id: str) -> dict:
    """
    Get the current status of a ServiceNow incident.

    This tool retrieves the current details of an incident including
    its state, assignments, and any updates.

    Args:
        incident_id: The sys_id of the incident to retrieve.

    Returns:
        Dictionary containing incident details:
        - number: Incident number
        - state: Current state
        - priority: Priority level
        - assigned_to: Assigned user
        - short_description: Brief description
        - Or error details if retrieval failed

    Example:
        status = get_incident_status("abc123...")
        print(f"Incident {status['number']} is {status['state']}")
    """
    client = _get_client()
    result = client.get_incident(sys_id=incident_id)

    if "error" in result:
        return result

    # Return a simplified status view
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


@tool
def search_incidents(
    text: str = "",
    states: list[str] | None = None,
    limit: int = 0,
    mode: str = "decision",
    raw_query: str = "",
) -> dict:
    """
    Search for incidents in ServiceNow.

    This tool is used for:
    - Deduplication before creating new incidents (mode="decision")
    - Knowledge base lookups using resolved/closed incidents (mode="knowledge")

    Args:
        text: Free-text query to search incident fields.
        states: Optional list of incident states to filter by.
        limit: Maximum number of incidents to return.
               Defaults to config value (typically 5).
        mode: Search mode.
              - "decision": lightweight results for deduplication
              - "knowledge": enriched results for resolution lookup
        raw_query: Optional raw ServiceNow sysparm_query string.
                   If provided, structured fields are ignored.

    Returns:
        Dictionary containing:
        - count: Number of matching incidents
        - results: List of matching incident summaries
        - Or error details
    """
    client = _get_client()

    results = client.search_incidents(
        text=text or None,
        states=states,
        limit=limit or None,
        mode=mode,
        raw_query=raw_query or None,
    )

    if results and "error" in results[0]:
        return results[0]

    return {
        "count": len(results),
        "results": results,
    }
