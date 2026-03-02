"""
Swarm Coordinator Module

Implements multi-agent coordination using the Strands SDK Swarm pattern.
Enables autonomous collaboration between specialist agents.
"""

from strands.multiagent import Swarm

from ..agents import CodingAgent, DataDogAgent, S3Agent, ServiceNowAgent
from ..utils.config_loader import load_settings
from ..utils.logging_config import get_logger

logger = get_logger("workflows.swarm")


class AIOpsSwarm:
    """
    Multi-Agent Swarm for AIOps operations.

    Coordinates specialist agents using the Strands SDK Swarm pattern,
    enabling autonomous agent collaboration with shared context and handoffs.

    Agents:
    - DataDog Agent: Fetches and formats logs
    - Coding Agent: Analyzes errors and suggests fixes
    - ServiceNow Agent: Creates incident tickets
    - S3 Agent: Stores reports to S3

    Usage:
        swarm = AIOpsSwarm()
        result = swarm.run("Analyze errors and create tickets")
        print(result.summary)
    """

    def __init__(
        self,
        model_id: str | None = None,
        region: str | None = None,
        include_datadog: bool = True,
        include_s3: bool = True,
    ):
        """
        Initialize the AIOps Swarm.

        Args:
            model_id: Optional Bedrock model ID for all agents.
            region: Optional AWS region override.
            include_datadog: Include DataDog agent in swarm.
            include_s3: Include S3 agent in swarm.
        """
        settings = load_settings()
        rate_limits = settings.get("rate_limits", {})

        self._max_handoffs = rate_limits.get("max_handoffs", 15)
        self._max_iterations = rate_limits.get("max_agent_iterations", 20)
        self._execution_timeout = rate_limits.get("execution_timeout_seconds", 900)
        self._node_timeout = rate_limits.get("node_timeout_seconds", 300)

        # Initialize agents
        self._datadog_agent = (
            DataDogAgent(model_id=model_id, region=region) if include_datadog else None
        )
        self._coding_agent = CodingAgent(model_id=model_id, region=region)
        self._servicenow_agent = ServiceNowAgent(model_id=model_id, region=region)
        self._s3_agent = S3Agent(model_id=model_id, region=region) if include_s3 else None

        # Create the swarm
        self._swarm = self._create_swarm()

        logger.info(f"Initialized AIOps Swarm with {self._max_handoffs} max handoffs")

    def _create_swarm(self) -> Swarm:
        """Create the Strands Swarm with agents."""
        agents = [
            self._coding_agent.inner_agent,
            self._servicenow_agent.inner_agent,
        ]

        if self._datadog_agent:
            agents.insert(0, self._datadog_agent.inner_agent)

        if self._s3_agent:
            agents.append(self._s3_agent.inner_agent)

        return Swarm(
            nodes=agents,
            max_handoffs=self._max_handoffs,
            max_iterations=self._max_iterations,
            execution_timeout=self._execution_timeout,
            node_timeout=self._node_timeout,
        )

    @property
    def datadog_agent(self) -> DataDogAgent | None:
        return self._datadog_agent

    @property
    def coding_agent(self) -> CodingAgent:
        return self._coding_agent

    @property
    def servicenow_agent(self) -> ServiceNowAgent:
        return self._servicenow_agent

    @property
    def s3_agent(self) -> S3Agent | None:
        return self._s3_agent

    def run(
        self, task: str, start_agent: str | None = None, precheck_servicenow: bool = True
    ) -> "SwarmResult":
        """
        Run a task through the swarm with optional ServiceNow pre-check.

        Args:
            task: Task description for the swarm.
            start_agent: Optional agent name to start with.
            precheck_servicenow: If True, ServiceNow searches for resolved tickets
                                before invoking CodingAgent.

        Returns:
            SwarmResult with execution details.
        """
        logger.info(f"Starting swarm task: {task[:100]}...")

        try:
            # Determine starting agent
            if precheck_servicenow and self._servicenow_agent:
                # Start with ServiceNow for ticket knowledge-base check
                start_agent_name = self._servicenow_agent.agent_name
            else:
                # Default start agent
                start_agent_name = start_agent or self._coding_agent.agent_name

            # Optionally, annotate the task for ServiceNow pre-check
            if precheck_servicenow:
                task = (
                    f"Step 1: Search ServiceNow for resolved tickets similar to this issue.\n"
                    f"If a resolved ticket exists, return the ticket number and skip further analysis.\n"
                    f"Otherwise, continue with full analysis and ticket creation.\n\n"
                    f"{task}"
                )

            result = self._swarm(task, start=start_agent_name)

            logger.info("Swarm task completed")

            return SwarmResult(
                success=True,
                task=task,
                output=str(result),
                agents_used=self._get_agents_used(),
                summary=self._generate_summary(),
            )

        except Exception as e:
            logger.error(f"Swarm task failed: {e}")

            return SwarmResult(
                success=False,
                task=task,
                output="",
                error=str(e),
                agents_used=self._get_agents_used(),
                summary=f"Task failed: {e}",
            )

    def _get_agents_used(self) -> list[str]:
        """Get list of agents that performed actions."""
        agents = []

        if self._datadog_agent and self._datadog_agent.state.total_invocations > 0:
            agents.append("DataDog")
        if self._coding_agent.state.total_invocations > 0:
            agents.append("Coding")
        if self._servicenow_agent.state.total_invocations > 0:
            agents.append("ServiceNow")
        if self._s3_agent and self._s3_agent.state.total_invocations > 0:
            agents.append("S3")

        return agents

    def _generate_summary(self) -> str:
        """Generate execution summary."""
        lines = ["## Swarm Execution Summary", ""]

        for agent, name in [
            (self._datadog_agent, "DataDog"),
            (self._coding_agent, "Coding"),
            (self._servicenow_agent, "ServiceNow"),
            (self._s3_agent, "S3"),
        ]:
            if agent and agent.state.total_invocations > 0:
                lines.append(f"### {name} Agent")
                lines.append(f"- Actions: {agent.state.total_invocations}")
                lines.append(f"- Successful: {agent.state.successful_invocations}")
                lines.append("")

        return "\n".join(lines)

    def reset(self) -> None:
        """Reset all agent states."""
        if self._datadog_agent:
            self._datadog_agent.reset_state()
        self._coding_agent.reset_state()
        self._servicenow_agent.reset_state()
        if self._s3_agent:
            self._s3_agent.reset_state()
        logger.info("Swarm agents reset")


class SwarmResult:
    """Result from a swarm execution."""

    def __init__(
        self,
        success: bool,
        task: str,
        output: str,
        agents_used: list[str],
        summary: str,
        error: str = "",
    ):
        self.success = success
        self.task = task
        self.output = output
        self.agents_used = agents_used
        self.summary = summary
        self.error = error

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "task": self.task,
            "output": self.output,
            "agents_used": self.agents_used,
            "summary": self.summary,
            "error": self.error,
        }
