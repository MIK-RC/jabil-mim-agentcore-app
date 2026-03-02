"""
Proactive Workflow Module

Implements the proactive analysis workflow that runs as an ECS task.
Uses ThreadPoolExecutor for parallel processing and Swarm for agent coordination.
"""

import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime

from ..agents import DataDogAgent, S3Agent
from ..tools.msteams_tool import MSTeamsClient
from ..utils.config_loader import load_settings
from ..utils.logging_config import get_logger
from .swarm_coordinator import AIOpsSwarm

logger = get_logger("workflows.proactive")


@dataclass
class ServiceResult:
    """Result of processing a single service."""

    service_name: str
    success: bool
    severity: str
    ticket_number: str | None
    s3_uri: str | None
    error: str | None
    duration_seconds: float
    agents_used: list[str]


class ProactiveWorkflow:
    """
    Proactive Analysis Workflow for ECS execution.

    Triggered by External trigger (As a Cron Job), this workflow:
    1. Fetches all services with errors/warnings from DataDog
    2. Processes each service in parallel using ThreadPoolExecutor
    3. Uses AIOpsSwarm for agent coordination per service
    4. Uploads individual reports and summary to S3

    Architecture:
        DataDog Agent (fetch all) → ThreadPoolExecutor
                                        ├── Service A → Swarm (Coding, ServiceNow, S3)
                                        ├── Service B → Swarm (Coding, ServiceNow, S3)
                                        └── Service C → Swarm (Coding, ServiceNow, S3)
                                    → S3 Summary
    """

    def __init__(self):
        """Initialize the proactive workflow."""
        settings = load_settings()
        workflow_config = settings.get("workflow", {})

        self._time_from = workflow_config.get("default_time_from", "now-1d")
        self._time_to = workflow_config.get("default_time_to", "now")
        self._max_workers = workflow_config.get("max_workers", 50)

        # DataDog agent for initial log fetch
        self._datadog_agent = DataDogAgent()

        # S3 agent for summary upload
        self._s3_agent = S3Agent()

        # MS Teams Client
        self._msteams_client = MSTeamsClient()

        # Workflow state
        self._start_time: datetime | None = None
        self._end_time: datetime | None = None

        logger.info(f"Initialized ProactiveWorkflow: max_workers={self._max_workers}")

    def _upload_service_report(
        self,
        service_result: ServiceResult,
        destination_sink: str = "s3",
    ) -> None:
        """
        Upload or send a single service report to the specified destination.

        Args:
            service_result: ServiceResult object containing details for this service.
            destination_sink: 's3' or 'msteams'
        """
        if not service_result.success:
            return  # Skip failed services

        # Generate content for the individual service report
        content = (
            f"# Service Report: {service_result.service_name}\n\n"
            f"- Severity: {service_result.severity}\n"
            f"- Ticket Number: {service_result.ticket_number or 'N/A'}\n"
            f"- Duration: {service_result.duration_seconds:.2f} sec\n"
            f"- Agents Used: {', '.join(service_result.agents_used) if service_result.agents_used else 'None'}\n"
        )

        if destination_sink == "s3":
            result = self._s3_agent.upload_report(
                service_name=service_result.service_name,
                content=content,
            )
            if result.get("success"):
                logger.info(f"Individual report uploaded to S3: {result.get('s3_uri')}")
            else:
                logger.error(
                    f"Failed to upload individual report for {service_result.service_name}: {result.get('error')}"
                )

        elif destination_sink == "msteams":
            result = self._msteams_client.send_notification(
                agent_id=f"service-{service_result.service_name}",
                message=content,
            )
            if result.get("success"):
                logger.info(f"Individual report sent to MS Teams: {service_result.service_name}")
            else:
                logger.error(
                    f"Failed to send individual report to MS Teams for {service_result.service_name}: {result.get('error')}"
                )

    def run(self, destination_sink: str) -> dict:
        """
        Execute the proactive workflow.

        Returns:
            Dictionary containing the complete workflow report.
        """

        self._start_time = datetime.now(UTC)
        logger.info("=" * 50)
        logger.info("PROACTIVE WORKFLOW RUN STARTING")
        logger.info(f"Time range: {self._time_from} to {self._time_to}")
        logger.info(f"Max workers: {self._max_workers}")
        logger.info("=" * 50)
        sys.stdout.flush()

        try:
            # Step 1: Fetch all logs and identify affected services
            logs, services = self._fetch_affected_services()

            if not services:
                logger.info("No services with issues found")
                return self._build_report([])

            logger.info(f"Found {len(services)} services with issues")

            # Step 2: Prepare data for each service
            service_data = self._prepare_service_data(logs, services)

            # Step 3: Process services in parallel using Swarm
            results = self._process_services_parallel(service_data)

            # Step 4: Generate and upload summary
            self._upload_summary(results=results, destination_sink=destination_sink)

            # Step 5: Build final report
            self._end_time = datetime.now(UTC)
            return self._build_report(results)

        except Exception as e:
            self._end_time = datetime.now(UTC)
            logger.error(f"Workflow failed: {e}")

            return {
                "success": False,
                "error": str(e),
                "execution_time_seconds": self._get_execution_time(),
                "timestamp": self._start_time.isoformat() if self._start_time else None,
            }

    def _fetch_affected_services(self) -> tuple[list[dict], list[str]]:
        """Fetch logs and extract affected services."""
        logger.info(f"Fetching logs: {self._time_from} to {self._time_to}")

        logs = self._datadog_agent.fetch_logs(
            time_from=self._time_from,
            time_to=self._time_to,
        )

        services = self._datadog_agent.get_services(logs)

        return logs, services

    def _prepare_service_data(
        self,
        logs: list[dict],
        services: list[str],
    ) -> list[dict]:
        """Prepare log data for each service."""
        service_data = []

        for service in services:
            formatted = self._datadog_agent.format_logs(logs, service=service)

            service_data.append(
                {
                    "service_name": service,
                    "formatted_logs": formatted,
                }
            )

        return service_data

    def _process_services_parallel(
        self,
        service_data: list[dict],
    ) -> list[ServiceResult]:
        """Process all services in parallel using Swarm."""
        results = []

        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            future_to_service = {
                executor.submit(
                    self._process_single_service,
                    data["service_name"],
                    data["formatted_logs"],
                ): data["service_name"]
                for data in service_data
            }

            for future in as_completed(future_to_service):
                service_name = future_to_service[future]
                try:
                    result = future.result()
                    results.append(result)
                    logger.info(
                        f"Completed {service_name}: "
                        f"success={result.success}, "
                        f"severity={result.severity}"
                    )
                except Exception as e:
                    logger.error(f"Failed to process {service_name}: {e}")
                    results.append(
                        ServiceResult(
                            service_name=service_name,
                            success=False,
                            severity="unknown",
                            ticket_number=None,
                            s3_uri=None,
                            error=str(e),
                            duration_seconds=0,
                            agents_used=[],
                        )
                    )

        return results

    def _process_single_service(
        self,
        service_name: str,
        formatted_logs: str,
    ) -> ServiceResult:
        """
        Process a single service using the Swarm with ServiceNow pre-check.
        """
        start_time = datetime.now(UTC)
        logger.info(f"Processing service with Swarm: {service_name}")

        try:
            swarm = AIOpsSwarm(include_datadog=False, include_s3=True)

            task = f"""Analyze the following logs for service '{service_name}':
{formatted_logs}

Please:
1. First, check ServiceNow for any resolved tickets similar to this issue.
- If found, return the ticket number and skip analysis.
2. Identify error patterns and assess severity (critical/high/medium/low)
3. Suggest fixes for the issues found
4. If severity is medium or higher, create a ServiceNow ticket
5. Upload a comprehensive report to S3 that includes:
- Analysis & severity assessment
- Suggested fixes
- ServiceNow ticket number (if created)

Service name: {service_name}
"""

            swarm_result = swarm.run(task, precheck_servicenow=True)

            severity = self._extract_severity(swarm_result.output)
            ticket_number = self._extract_ticket_number(swarm_result.output)
            s3_uri = self._extract_s3_uri(swarm_result.output)

            duration = (datetime.now(UTC) - start_time).total_seconds()

            return ServiceResult(
                service_name=service_name,
                success=swarm_result.success,
                severity=severity,
                ticket_number=ticket_number,
                s3_uri=s3_uri,
                error=swarm_result.error if not swarm_result.success else None,
                duration_seconds=duration,
                agents_used=swarm_result.agents_used,
            )

        except Exception as e:
            duration = (datetime.now(UTC) - start_time).total_seconds()
            logger.error(f"Failed to process {service_name}: {e}")

            return ServiceResult(
                service_name=service_name,
                success=False,
                severity="unknown",
                ticket_number=None,
                s3_uri=None,
                error=str(e),
                duration_seconds=duration,
                agents_used=[],
            )

    def _extract_severity(self, output: str) -> str:
        """Extract severity from Swarm output."""
        output_lower = output.lower()
        if "critical" in output_lower:
            return "critical"
        elif "high" in output_lower:
            return "high"
        elif "medium" in output_lower:
            return "medium"
        return "low"

    def _extract_ticket_number(self, output: str) -> str | None:
        """Extract ticket number from Swarm output."""

        match = re.search(r"INC\d+", output)
        return match.group(0) if match else None

    def _extract_s3_uri(self, output: str) -> str | None:
        """Extract S3 URI from Swarm output."""

        match = re.search(r"s3://[^\s]+", output)
        return match.group(0) if match else None

    def _upload_summary(
        self,
        results: list[ServiceResult],
        destination_sink: str = "s3",
        upload_individual_reports: bool = True,
    ) -> None:
        """
        Generate and upload/send the summary report.
        Optionally upload/send individual service reports as well.

        Args:
            results: List of ServiceResult objects.
            destination_sink: 's3' or 'msteams'
            upload_individual_reports: Whether to send individual reports.
        """
        # --- Generate summary content ---
        summary_content = self._generate_summary(results)

        # --- Upload or send the summary ---
        if destination_sink == "s3":
            result = self._s3_agent.upload_summary(summary_content)
            if result.get("success"):
                logger.info(f"Summary uploaded to S3: {result.get('s3_uri')}")
            else:
                logger.error(f"Failed to upload summary to S3: {result.get('error')}")
        elif destination_sink == "msteams":
            result = self._msteams_client.send_notification(
                agent_id="proactive-workflow",
                message=summary_content,
            )
            if result.get("success"):
                logger.info("Summary sent to MS Teams successfully")
            else:
                logger.error(f"Failed to send summary to MS Teams: {result.get('error')}")

        # --- Optionally upload/send individual service reports ---
        if upload_individual_reports:
            for service_result in results:
                self._upload_service_report(service_result, destination_sink=destination_sink)

    def _generate_summary(self, results: list[ServiceResult]) -> str:
        """Generate a clean summary report."""
        now = datetime.now(UTC)
        successful = [r for r in results if r.success]
        failed = [r for r in results if not r.success]

        severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for r in successful:
            if r.severity in severity_counts:
                severity_counts[r.severity] += 1

        tickets_created = [r for r in successful if r.ticket_number]

        lines = [
            "# Proactive Analysis Summary",
            "",
            f"Generated: {now.strftime('%Y-%m-%d %H:%M:%S UTC')}",
            f"Time range: {self._time_from} to {self._time_to}",
            "",
            "## Overview",
            f"- Services processed: {len(results)}",
            f"- Successful: {len(successful)}",
            f"- Failed: {len(failed)}",
            f"- Tickets created: {len(tickets_created)}",
            "",
            "## Severity Breakdown",
            f"- Critical: {severity_counts['critical']}",
            f"- High: {severity_counts['high']}",
            f"- Medium: {severity_counts['medium']}",
            f"- Low: {severity_counts['low']}",
            "",
        ]

        if tickets_created:
            lines.append("## Tickets Created")
            for r in tickets_created:
                lines.append(f"- {r.ticket_number}: {r.service_name} ({r.severity.upper()})")
            lines.append("")

        if successful:
            lines.append("## Service Reports")
            for r in successful:
                agents = ", ".join(r.agents_used) if r.agents_used else "None"
                lines.append(f"- {r.service_name} [{r.severity.upper()}] - Agents: {agents}")
                if r.s3_uri:
                    lines.append(f"  Report: {r.s3_uri}")
            lines.append("")

        if failed:
            lines.append("## Failed Services")
            for r in failed:
                lines.append(f"- {r.service_name}: {r.error}")
            lines.append("")

        execution_time = self._get_execution_time()
        lines.append(f"Total execution time: {execution_time:.2f} seconds")

        return "\n".join(lines)

    def _build_report(self, results: list[ServiceResult]) -> dict:
        """Build the final workflow report dictionary."""
        successful = [r for r in results if r.success]
        failed = [r for r in results if not r.success]

        severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for r in successful:
            if r.severity in severity_counts:
                severity_counts[r.severity] += 1

        return {
            "success": True,
            "timestamp": self._start_time.isoformat() if self._start_time else None,
            "execution_time_seconds": self._get_execution_time(),
            "time_range": {
                "from": self._time_from,
                "to": self._time_to,
            },
            "services": {
                "total": len(results),
                "successful": len(successful),
                "failed": len(failed),
            },
            "severity_breakdown": severity_counts,
            "tickets_created": [
                {"service": r.service_name, "ticket": r.ticket_number, "severity": r.severity}
                for r in successful
                if r.ticket_number
            ],
            "reports_uploaded": [
                {"service": r.service_name, "s3_uri": r.s3_uri} for r in successful if r.s3_uri
            ],
            "errors": [{"service": r.service_name, "error": r.error} for r in failed],
        }

    def _get_execution_time(self) -> float:
        """Get the execution time in seconds."""
        if not self._start_time:
            return 0

        end = self._end_time or datetime.now(UTC)
        return (end - self._start_time).total_seconds()


def run_proactive_workflow(destination_sink: str) -> dict:
    """
    Convenience function to run the proactive workflow.

    Returns:
        Workflow report dictionary.
    """
    workflow = ProactiveWorkflow()
    return workflow.run(destination_sink=destination_sink)
