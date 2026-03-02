"""
DataDog Agent Module

Specialist agent for fetching and analyzing logs from DataDog.
Can be used standalone or as part of the multi-agent swarm.
"""

from ..tools.datadog_tools import (
    DataDogClient,
    extract_unique_services,
    format_logs_for_analysis,
    query_logs,
)
from .base import BaseAgent


class DataDogAgent(BaseAgent):
    """
    DataDog Specialist Agent for log analysis.

    Responsibilities:
    - Query error and warning logs from DataDog
    - Extract unique services from log data
    - Format logs for downstream analysis
    - Identify patterns in log data

    Standalone Usage:
        agent = DataDogAgent()

        # Simple invocation
        result = agent.invoke("Get all error logs from the last hour")

        # Direct tool access
        logs = agent.fetch_logs(time_from="now-1h")
        services = agent.get_services(logs)

    Swarm Usage:
        # The agent's inner_agent can be used in a Swarm
        from strands.multiagent import Swarm
        swarm = Swarm(agents=[datadog_agent.inner_agent, ...])
    """

    def __init__(
        self,
        model_id: str | None = None,
        region: str | None = None,
        api_key: str | None = None,
        app_key: str | None = None,
        datadog_site: str | None = None,
    ):
        """
        Initialize the DataDog Agent.

        Args:
            model_id: Optional Bedrock model ID override.
            region: Optional AWS region override.
            api_key: Optional DataDog API key (defaults to env var).
            app_key: Optional DataDog Application key (defaults to env var).
            datadog_site: Optional DataDog site (us1, us5, eu1, etc.).
        """
        # Initialize the DataDog client for direct tool access
        self._datadog_client = DataDogClient(
            api_key=api_key,
            app_key=app_key,
            site=datadog_site,
        )

        super().__init__(
            agent_type="datadog",
            model_id=model_id,
            region=region,
        )

    def get_tools(self) -> list:
        """Get the DataDog-specific tools."""
        return [
            query_logs,
            extract_unique_services,
            format_logs_for_analysis,
        ]

    # ==========================================
    # Direct Tool Access Methods (Standalone Use)
    # ==========================================

    def fetch_logs(
        self,
        time_from: str = "now-1d",
        time_to: str = "now",
        query: str = "status:(error OR warn)",
        limit: int = 50,
    ) -> list[dict]:
        """
        Fetch logs directly without agent invocation.

        Use this for programmatic access when you don't need
        LLM reasoning, just the raw data.

        Args:
            time_from: Start time in DataDog time syntax.
            time_to: End time in DataDog time syntax.
            query: DataDog query string.
            limit: Maximum number of logs.

        Returns:
            List of log entries from DataDog.
        """
        self._logger.info(f"Direct fetch: query='{query}', range={time_from} to {time_to}")

        logs = self._datadog_client.query_logs(
            time_from=time_from,
            time_to=time_to,
            query=query,
            limit=limit,
        )

        self.record_action(
            action_type="direct_fetch",
            description=f"Fetched {len(logs)} logs from DataDog",
            input_summary=f"query={query}, limit={limit}",
            output_summary=f"Retrieved {len(logs)} log entries",
        )

        return logs

    def get_services(self, logs: list[dict]) -> list[str]:
        """
        Extract unique services from logs.

        Args:
            logs: List of log entries.

        Returns:
            Sorted list of unique service names.
        """
        services = self._datadog_client.extract_services(logs)
        return sorted(list(services))

    def format_logs(
        self,
        logs: list[dict],
        service: str | None = None,
        max_logs: int = 30,
    ) -> str:
        """
        Format logs for analysis.

        Args:
            logs: List of log entries.
            service: Optional service to filter by.
            max_logs: Maximum logs to include.

        Returns:
            Formatted string of log entries.
        """
        return self._datadog_client.format_logs(
            logs=logs,
            service=service,
            max_logs=max_logs,
        )

    def analyze_service_logs(
        self,
        service_name: str,
        time_from: str = "now-1d",
        time_to: str = "now",
    ) -> dict:
        """
        Convenience method to fetch and format logs for a specific service.

        Args:
            service_name: Name of the service to analyze.
            time_from: Start time.
            time_to: End time.

        Returns:
            Dictionary with logs and formatted context.
        """
        # Fetch logs filtered by service
        query = f"service:{service_name} status:(error OR warn)"
        logs = self.fetch_logs(
            time_from=time_from,
            time_to=time_to,
            query=query,
        )

        # Format for analysis
        formatted = self.format_logs(logs)

        return {
            "service": service_name,
            "log_count": len(logs),
            "time_range": {"from": time_from, "to": time_to},
            "raw_logs": logs,
            "formatted_context": formatted,
        }

    def get_daily_error_summary(self) -> dict:
        """
        Get a summary of errors from the last 24 hours.

        Returns:
            Dictionary with error summary by service.
        """
        logs = self.fetch_logs(time_from="now-1d", time_to="now")
        services = self.get_services(logs)

        summary = {
            "total_logs": len(logs),
            "services_affected": services,
            "by_service": {},
        }

        for service in services:
            service_logs = [
                log for log in logs if log.get("attributes", {}).get("service") == service
            ]

            # Count by status
            error_count = sum(
                1 for log in service_logs if log.get("attributes", {}).get("status") == "error"
            )
            warn_count = len(service_logs) - error_count

            summary["by_service"][service] = {
                "total": len(service_logs),
                "errors": error_count,
                "warnings": warn_count,
            }

        self.record_action(
            action_type="daily_summary",
            description="Generated daily error summary",
            output_summary=f"Found {len(logs)} logs across {len(services)} services",
        )

        return summary
