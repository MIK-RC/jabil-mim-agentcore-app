import os

import requests
from strands import tool

from utils.config_loader import load_tools_config
from utils.logging_config import get_logger

logger = get_logger("snow_tools")



class ServiceNowClient:

    def __init__(self, instance: str | None = None, username: str | None = None, password: str | None = None):

        self._config = load_tools_config().get("servicenow", {})

        self._instance = instance or os.environ.get("SERVICENOW_INSTANCE")
        self._username = username or os.environ.get("SERVICENOW_USER", "")
        self._password = password or os.environ.get("SERVICENOW_PASS", "")

        if not self._instance:
            logger.warning("ServiceNow instance not configured")

        self._timeout = self._config.get("request", {}).get("timeout_seconds", 30)

    @property
    def get_base_url(self) -> str:
        """Get the base URL for the ServiceNow instance."""
        if not self._instance:
            return ""
        if self._instance.startswith("http"):
            return self._instance.rstrip("/")
        return f"https://{self._instance}"

    @property
    def prepare_auth(self) -> tuple[str, str]:
        """Get the authentication tuple."""
        return (self._username, self._password)

    @property
    def prepare_headers(self) -> dict[str, str]:
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

        if not self.get_base_url:
            logger.error("ServiceNow instance not configured")
            return {"error": "ServiceNow instance not configured"}

        defaults = self._config.get("defaults", {})
        endpoint = self._config.get("endpoints", {}).get("incidents", "/api/now/table/incident")
        url = f"{self.get_base_url}{endpoint}"

        impact, urgency = self._get_priority_values(priority)

        payload = {
            "short_description": short_description[:100],
            "description": description,
            "impact": impact,
            "urgency": urgency,
            "category": category or defaults.get("category", "LLM-Assisted Resolution"),
        }

        if assignment_group or defaults.get("assignment_group"):
            payload["assignment_group"] = assignment_group or defaults.get("assignment_group")

        if extra:
            payload.update(extra)

        logger.info(f"Creating ServiceNow incident: {short_description[:60]}...")

        try:
            response = requests.post(
                url,
                auth=self.prepare_auth(),
                headers=self.prepare_headers(),
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
        if not self.get_base_url():
            logger.error("ServiceNow instance not configured")
            return {"error": "ServiceNow instance not configured"}

        endpoint = self._config.get("endpoints", {}).get("incidents", "/api/now/table/incident")
        url = f"{self.get_base_url()}{endpoint}/{sys_id}"

        logger.info(f"Updating incident: {sys_id}")

        try:
            response = requests.patch(
                url,
                auth=self.prepare_auth(),
                headers=self.prepare_headers(),
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

        if not self.get_base_url():
            logger.error("ServiceNow instance not configured")
            return {"error": "ServiceNow instance not configured"}

        endpoint = self._config.get("endpoints", {}).get("incidents", "/api/now/table/incident")
        url = f"{self.get_base_url()}{endpoint}/{sys_id}"

        try:
            response = requests.get(
                url,
                auth=self.prepare_auth(),
                headers=self.prepare_headers(),
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

        if not self.get_base_url():
            logger.error("ServiceNow instance not configured")
            return [{"error": "ServiceNow instance not configured"}]

        search_cfg = self._config.get("search", {})
        endpoint = self._config.get("endpoints", {}).get("incidents", "/api/now/table/incident")

        url = f"{self.get_base_url()}{endpoint}"

        limit = limit or search_cfg.get("default_limit", 5)
        order = search_cfg.get("default_order", "ORDERBYDESCsys_updated_on")

        if not states:
            states = search_cfg.get("default_states", {}).get(mode, [])

        query_parts: list[str] = []

        if raw_query:
            query = raw_query
        else:
            if text:
                fields = search_cfg.get(
                    "searchable_fields",
                    ["short_description", "description", "close_notes"],
                )
                text_query = "^OR".join(f"{field}LIKE{text}" for field in fields)
                query_parts.append(f"({text_query})")

            if states:
                state_query = "^OR".join(f"state={state}" for state in states)
                query_parts.append(f"({state_query})")

            query = "^".join(query_parts) if query_parts else ""

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
                auth=self.prepare_auth(),
                headers=self.prepare_headers(),
                params=params,
                timeout=self._timeout,
            )
            response.raise_for_status()

            results = response.json().get("result", [])

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

    def delete_incident(
        self,
        sys_id: str,
    ) -> dict:
        if not self.get_base_url():
            logger.error("ServiceNow instance not configured")
            return {"error": "ServiceNow instance not configured"}

        endpoint = self._config.get("endpoints", {}).get("incidents", "/api/now/table/incident")
        url = f"{self.get_base_url()}{endpoint}/{sys_id}"

        logger.info(f"Deleting ServiceNow incident: {sys_id}")

        try:
            response = requests.delete(
                url,
                auth=self.prepare_auth(),
                headers=self.prepare_headers(),
                timeout=self._timeout,
            )
            response.raise_for_status()

            logger.info(f"Deleted incident: {sys_id}")

            return {"success": True, "sys_id": sys_id, "message": "Incident deleted successfully"}

        except requests.exceptions.Timeout:
            logger.error("ServiceNow API request timed out")
            return {"error": "Request timed out"}
        except requests.exceptions.RequestException as e:
            logger.error(f"ServiceNow delete failed: {e}")
            return {"error": str(e)}

_default_client: ServiceNowClient | None = None


def _get_client() -> ServiceNowClient:
    """Get or create the default ServiceNow client."""
    global _default_client
    if _default_client is None:
        _default_client = ServiceNowClient()
    return _default_client


@tool
def create_incident(short_description: str, description: str, priority: str = "medium", category: str = "") -> dict:
    client = _get_client()
    return client.create_incident(
        short_description=short_description,
        description=description,
        priority=priority,
        category=category if category else None,
    )


@tool
def update_incident(incident_id: str, work_notes: str = "", state: str = "", resolution_notes: str = "") -> dict:
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
def search_incidents(text: str = "", states: list[str] | None = None, limit: int = 0, mode: str = "decision", raw_query: str = "") -> dict:
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


@tool
def delete_incident(incident_id: str) -> dict:
    client = _get_client()
    return client.delete_incident(sys_id=incident_id)
