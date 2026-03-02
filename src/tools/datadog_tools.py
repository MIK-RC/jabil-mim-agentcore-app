"""
DataDog Tools Module

Tools for interacting with the DataDog API to query and analyze logs.
These tools can be used standalone or as part of the DataDog Agent.
"""

import os

import requests
from strands import tool

from ..utils.config_loader import load_tools_config
from ..utils.logging_config import get_logger

logger = get_logger("tools.datadog")


class DataDogClient:
    """
    DataDog API client for log queries and analysis.

    Can be used standalone or through the tool functions.

    Usage:
        # Standalone usage
        client = DataDogClient()
        logs = client.query_logs(time_from="now-1h", time_to="now")

        # With custom credentials
        client = DataDogClient(
            api_key="your-api-key",
            app_key="your-app-key",
            site="us5"
        )
    """

    def __init__(
        self,
        api_key: str | None = None,
        app_key: str | None = None,
        site: str | None = None,
    ):
        """
        Initialize the DataDog client.

        Args:
            api_key: DataDog API key. Defaults to DATADOG_API_KEY env var.
            app_key: DataDog Application key. Defaults to DATADOG_APP_KEY env var.
            site: DataDog site (us1, us3, us5, eu1, ap1). Defaults to config.
        """
        self._config = load_tools_config().get("datadog", {})

        self._api_key = api_key or os.environ.get("DATADOG_API_KEY")
        self._app_key = app_key or os.environ.get("DATADOG_APP_KEY")
        self._site = site or self._config.get("site", "us5")

        if not self._api_key or not self._app_key:
            logger.warning("DataDog API credentials not configured")

        self._base_url = f"https://api.{self._site}.datadoghq.com"
        self._timeout = self._config.get("request", {}).get("timeout_seconds", 30)

    @property
    def headers(self) -> dict[str, str]:
        """Get the authentication headers."""
        return {
            "DD-API-KEY": self._api_key or "",
            "DD-APPLICATION-KEY": self._app_key or "",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def query_logs(
        self,
        time_from: str = "now-1d",
        time_to: str = "now",
        query: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        """
        Query logs from DataDog.

        Args:
            time_from: Start time (DataDog time syntax, e.g., "now-1d", "now-1h")
            time_to: End time (DataDog time syntax)
            query: Log query string. Defaults to error/warning status.
            limit: Maximum number of logs to return.

        Returns:
            List of log entries with attributes.
        """
        query_config = self._config.get("query", {})

        effective_query = query or query_config.get("default_query", "status:(error OR warn)")
        effective_limit = limit or query_config.get("limit", 50)

        endpoint = self._config.get("endpoints", {}).get("logs_search", "/api/v2/logs/events/search")
        url = f"{self._base_url}{endpoint}"

        body = {
            "filter": {
                "from": time_from,
                "to": time_to,
                "query": effective_query,
            },
            "page": {"limit": effective_limit},
        }

        logger.info(f"Querying DataDog logs: query='{effective_query}', limit={effective_limit}")

        try:
            response = requests.post(
                url,
                headers=self.headers,
                json=body,
                timeout=self._timeout,
            )
            response.raise_for_status()

            data = response.json()
            logs = data.get("data", [])

            logger.info(f"Retrieved {len(logs)} log entries from DataDog")
            return logs

        except requests.exceptions.Timeout:
            logger.error("DataDog API request timed out")
            return []
        except requests.exceptions.RequestException as e:
            logger.error(f"DataDog API request failed: {e}")
            return []

    def extract_services(self, logs: list[dict]) -> set[str]:
        """
        Extract unique service names from log entries.

        Args:
            logs: List of log entries from query_logs.

        Returns:
            Set of unique service names.
        """
        services = set()

        for log in logs:
            try:
                service = log.get("attributes", {}).get("service")
                if service:
                    services.add(service)
            except (AttributeError, TypeError):
                continue

        logger.info(f"Extracted {len(services)} unique services: {services}")
        return services

    def format_logs(
        self,
        logs: list[dict],
        service: str | None = None,
        max_logs: int | None = None,
    ) -> str:
        """
        Format logs for LLM analysis.

        Args:
            logs: List of log entries.
            service: Optional service name to filter by.
            max_logs: Maximum number of logs to include.

        Returns:
            Formatted string suitable for LLM context.
        """
        formatting_config = self._config.get("formatting", {})

        max_logs = max_logs or formatting_config.get("max_logs_for_context", 30)
        max_message_length = formatting_config.get("max_message_length", 500)

        # Filter by service if specified
        if service:
            logs = [log for log in logs if log.get("attributes", {}).get("service") == service]

        # Limit number of logs
        logs = logs[:max_logs]

        formatted_entries = []

        for log in logs:
            attrs = log.get("attributes", {})

            timestamp = attrs.get("timestamp", "N/A")
            status = attrs.get("status", "N/A")
            service_name = attrs.get("service", "unknown")
            message = attrs.get("message", "No message")

            # Truncate long messages
            if len(message) > max_message_length:
                message = message[:max_message_length] + "..."

            # Take only first line of multi-line messages
            message = message.split("\n")[0].strip()

            formatted_entries.append(f"[{timestamp}] [{status.upper()}] [{service_name}] {message}")

        return "\n".join(formatted_entries)


# Create a default client instance for tool functions
_default_client: DataDogClient | None = None


def _get_client() -> DataDogClient:
    """Get or create the default DataDog client."""
    global _default_client
    if _default_client is None:
        _default_client = DataDogClient()
    return _default_client


@tool
def query_logs(
    time_from: str = "now-1d",
    time_to: str = "now",
    query: str = "status:(error OR warn)",
    limit: int = 50,
) -> list[dict]:
    """
    Query logs from DataDog for the specified time range and query.

    This tool fetches log entries from DataDog's Log Management API.
    Use it to retrieve error and warning logs for analysis.

    Args:
        time_from: Start time in DataDog time syntax (e.g., "now-1d", "now-1h", "now-30m").
                  Defaults to "now-1d" (last 24 hours).
        time_to: End time in DataDog time syntax. Defaults to "now".
        query: DataDog log query string. Defaults to "status:(error OR warn)".
               Examples: "service:my-app status:error", "host:prod-*"
        limit: Maximum number of logs to return. Defaults to 50.

    Returns:
        List of log entries, each containing:
        - attributes: dict with timestamp, status, service, message, host
        - id: unique log identifier

    Example:
        logs = query_logs(time_from="now-1h", query="service:payment-api status:error")
    """
    client = _get_client()
    return client.query_logs(
        time_from=time_from,
        time_to=time_to,
        query=query,
        limit=limit,
    )


@tool
def extract_unique_services(logs: list[dict]) -> list[str]:
    """
    Extract unique service names from a list of log entries.

    This tool parses DataDog log entries and extracts all unique
    service names, useful for identifying affected services.

    Args:
        logs: List of log entries from the query_logs tool.

    Returns:
        List of unique service names found in the logs.

    Example:
        logs = query_logs(time_from="now-1d")
        services = extract_unique_services(logs)
        # Returns: ["payment-api", "user-service", "notification-service"]
    """
    client = _get_client()
    services = client.extract_services(logs)
    return sorted(list(services))


@tool
def format_logs_for_analysis(
    logs: list[dict],
    service: str = "",
    max_logs: int = 30,
) -> str:
    """
    Format log entries into a structured string for LLM analysis.

    This tool converts raw log entries into a human-readable format
    suitable for analysis by other agents or LLMs.

    Args:
        logs: List of log entries from the query_logs tool.
        service: Optional service name to filter logs by.
                 If empty, all logs are included.
        max_logs: Maximum number of logs to include in output. Defaults to 30.

    Returns:
        Formatted string with one log entry per line in format:
        [timestamp] [STATUS] [service] message

    Example:
        formatted = format_logs_for_analysis(logs, service="payment-api", max_logs=20)
    """
    client = _get_client()
    service_filter = service if service else None
    return client.format_logs(logs, service=service_filter, max_logs=max_logs)
