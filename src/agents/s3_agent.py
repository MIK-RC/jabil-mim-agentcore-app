"""
S3 Agent Module

Specialist agent for storing analysis reports to Amazon S3.
Can be used standalone or as part of the multi-agent system.
"""

from ..tools.s3_tools import (
    S3Client,
    upload_service_report,
    upload_summary_report,
)
from .base import BaseAgent


class S3Agent(BaseAgent):
    """
    S3 Specialist Agent for report storage.

    Responsibilities:
    - Upload service-specific reports to S3
    - Upload summary reports to S3
    - Manage report organization by service and date

    Standalone Usage:
        agent = S3Agent()

        # Simple invocation with LLM reasoning
        result = agent.invoke("Upload a report for payment-service...")

        # Direct tool access
        result = agent.upload_report("payment-service", "# Report content...")

    Swarm Usage:
        # The agent's inner_agent can be used in a Swarm
        from strands.multiagent import Swarm
        swarm = Swarm(agents=[s3_agent.inner_agent, ...])
    """

    def __init__(
        self,
        model_id: str | None = None,
        region: str | None = None,
        bucket: str | None = None,
    ):
        """
        Initialize the S3 Agent.

        Args:
            model_id: Optional Bedrock model ID override.
            region: Optional AWS region override.
            bucket: Optional S3 bucket name (defaults to S3_REPORTS_BUCKET env var).
        """
        # Initialize the S3 client for direct tool access
        self._s3_client = S3Client(
            bucket=bucket,
            region=region,
        )

        super().__init__(
            agent_type="s3",
            model_id=model_id,
            region=region,
        )

    def get_tools(self) -> list:
        """Get the S3-specific tools."""
        return [
            upload_service_report,
            upload_summary_report,
        ]

    # ==========================================
    # Direct Tool Access Methods (Standalone Use)
    # ==========================================

    def upload_report(
        self,
        service_name: str,
        content: str,
        timestamp: str | None = None,
    ) -> dict:
        """
        Upload a service report to S3 directly.

        Use this for programmatic access when you don't need
        LLM reasoning, just direct upload.

        Args:
            service_name: Name of the service.
            content: Markdown content of the report.
            timestamp: Optional timestamp for the filename.

        Returns:
            Dictionary with upload result.
        """
        self._logger.info(f"Uploading report for service: {service_name}")

        result = self._s3_client.upload_report(service_name, content, timestamp)

        self.record_action(
            action_type="upload_report",
            description=f"Uploaded report for {service_name}",
            input_summary=f"Service: {service_name}, Content: {len(content)} chars",
            output_summary=result.get("s3_uri", result.get("error", "Unknown")),
            success=result.get("success", False),
            error_message=result.get("error", ""),
        )

        return result

    def upload_summary(
        self,
        content: str,
        timestamp: str | None = None,
    ) -> dict:
        """
        Upload a summary report to S3 directly.

        Use this for programmatic access when you don't need
        LLM reasoning, just direct upload.

        Args:
            content: Markdown content of the summary.
            timestamp: Optional timestamp for the filename.

        Returns:
            Dictionary with upload result.
        """
        self._logger.info("Uploading summary report")

        result = self._s3_client.upload_summary(content, timestamp)

        self.record_action(
            action_type="upload_summary",
            description="Uploaded summary report",
            input_summary=f"Content: {len(content)} chars",
            output_summary=result.get("s3_uri", result.get("error", "Unknown")),
            success=result.get("success", False),
            error_message=result.get("error", ""),
        )

        return result
