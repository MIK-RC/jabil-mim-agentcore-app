"""
Coding Agent Module

Specialist agent for error analysis and code fix suggestions.
Can be used standalone or as part of the multi-agent swarm.
"""

from ..tools.code_analysis_tools import (
    CodeAnalyzer,
    analyze_error_patterns,
    assess_severity,
    suggest_code_fix,
)
from .base import BaseAgent


class CodingAgent(BaseAgent):
    """
    Coding Specialist Agent for error analysis and fix suggestions.

    Responsibilities:
    - Analyze log data to identify root causes
    - Detect common error patterns
    - Suggest code fixes with examples
    - Assess severity of identified issues

    Standalone Usage:
        agent = CodingAgent()

        # Simple invocation with LLM reasoning
        result = agent.invoke("Analyze these errors and suggest fixes: [logs]")

        # Direct tool access
        patterns = agent.analyze_logs(formatted_log_context)
        fixes = agent.get_fix_suggestions(patterns, "payment-api")

    Swarm Usage:
        # The agent's inner_agent can be used in a Swarm
        from strands.multiagent import Swarm
        swarm = Swarm(agents=[coding_agent.inner_agent, ...])
    """

    def __init__(
        self,
        model_id: str | None = None,
        region: str | None = None,
    ):
        """
        Initialize the Coding Agent.

        Args:
            model_id: Optional Bedrock model ID override.
            region: Optional AWS region override.
        """
        # Initialize the code analyzer for direct tool access
        self._analyzer = CodeAnalyzer()

        super().__init__(
            agent_type="coding",
            model_id=model_id,
            region=region,
        )

    def get_tools(self) -> list:
        """Get the coding-specific tools."""
        return [
            analyze_error_patterns,
            suggest_code_fix,
            assess_severity,
        ]

    # ==========================================
    # Direct Tool Access Methods (Standalone Use)
    # ==========================================

    def analyze_logs(self, log_context: str) -> dict:
        """
        Analyze log context to identify error patterns.

        Use this for programmatic access when you don't need
        LLM reasoning, just pattern analysis.

        Args:
            log_context: Formatted log entries as string.

        Returns:
            Dictionary with identified patterns.
        """
        self._logger.info("Analyzing log context for error patterns")

        patterns = self._analyzer.analyze_patterns(log_context)

        self.record_action(
            action_type="analyze_patterns",
            description=f"Analyzed logs, found {len(patterns.get('error_types', []))} error types",
            input_summary=f"Log context: {len(log_context)} chars",
            output_summary=f"Error types: {patterns.get('error_types', [])}",
        )

        return patterns

    def get_fix_suggestions(
        self,
        patterns: dict,
        service_name: str = "",
    ) -> list[dict]:
        """
        Generate fix suggestions for identified patterns.

        Args:
            patterns: Dictionary from analyze_logs.
            service_name: Name of the affected service.

        Returns:
            List of fix suggestions with code snippets.
        """
        self._logger.info(f"Generating fix suggestions for {service_name or 'unknown service'}")

        suggestions = self._analyzer.suggest_fixes(patterns, service_name)

        self.record_action(
            action_type="suggest_fixes",
            description=f"Generated {len(suggestions)} fix suggestions",
            input_summary=f"Service: {service_name}, Patterns: {patterns.get('error_types', [])}",
            output_summary=f"Suggestions: {[s.get('error_type') for s in suggestions]}",
        )

        return suggestions

    def get_severity(self, patterns: dict) -> dict:
        """
        Assess severity of identified error patterns.

        Args:
            patterns: Dictionary from analyze_logs.

        Returns:
            Severity assessment with recommendation.
        """
        severity = self._analyzer.assess_severity(patterns)

        error_count = len(patterns.get("error_types", []))
        recurring_count = len(patterns.get("recurring_issues", []))

        recommendations = {
            "critical": "Immediate action required. Escalate to on-call team.",
            "high": "Urgent attention needed. Create high-priority ticket.",
            "medium": "Should be addressed soon. Schedule for next sprint.",
            "low": "Monitor and address when convenient.",
        }

        return {
            "severity": severity,
            "error_count": error_count,
            "recurring_count": recurring_count,
            "affected_services": patterns.get("affected_services", []),
            "recommendation": recommendations.get(severity, "Review and assess"),
        }

    def full_analysis(
        self,
        log_context: str,
        service_name: str = "",
    ) -> dict:
        """
        Perform a complete analysis of log context.

        This is a convenience method that runs the full analysis pipeline:
        1. Analyze error patterns
        2. Assess severity
        3. Generate fix suggestions

        Args:
            log_context: Formatted log entries.
            service_name: Name of the affected service.

        Returns:
            Complete analysis report.
        """
        # Step 1: Analyze patterns
        patterns = self.analyze_logs(log_context)

        # Step 2: Assess severity
        severity_assessment = self.get_severity(patterns)

        # Step 3: Get fix suggestions
        suggestions = self.get_fix_suggestions(patterns, service_name)

        report = {
            "service": service_name or "Unknown",
            "patterns": patterns,
            "severity": severity_assessment,
            "suggestions": suggestions,
            "summary": self._generate_summary(patterns, severity_assessment, suggestions),
        }

        self.record_action(
            action_type="full_analysis",
            description=f"Completed full analysis for {service_name or 'unknown'}",
            input_summary=f"Log context: {len(log_context)} chars",
            output_summary=f"Severity: {severity_assessment['severity']}, "
            f"Suggestions: {len(suggestions)}",
        )

        return report

    def _generate_summary(
        self,
        patterns: dict,
        severity: dict,
        suggestions: list[dict],
    ) -> str:
        """Generate a human-readable summary of the analysis."""
        lines = [
            "## Analysis Summary",
            "",
            f"**Severity Level:** {severity['severity'].upper()}",
            f"**Recommendation:** {severity['recommendation']}",
            "",
            "### Findings",
            f"- Error types identified: {len(patterns.get('error_types', []))}",
            f"- Recurring issues: {len(patterns.get('recurring_issues', []))}",
            f"- Services affected: {', '.join(patterns.get('affected_services', ['None']))}",
            "",
        ]

        if patterns.get("potential_causes"):
            lines.append("### Potential Causes")
            for cause in patterns["potential_causes"]:
                lines.append(f"- {cause}")
            lines.append("")

        if suggestions:
            lines.append("### Suggested Fixes")
            for i, suggestion in enumerate(suggestions, 1):
                lines.append(
                    f"{i}. **{suggestion.get('error_type', 'General')}**: "
                    f"{suggestion.get('suggestion', 'Review code')}"
                )
            lines.append("")

        return "\n".join(lines)

    def analyze_with_llm(
        self,
        log_context: str,
        additional_context: str = "",
    ) -> str:
        """
        Use LLM reasoning to analyze logs and provide insights.

        This method leverages the full power of the LLM to provide
        detailed analysis beyond pattern matching.

        Args:
            log_context: Formatted log entries.
            additional_context: Any additional context (e.g., recent changes).

        Returns:
            LLM-generated analysis and recommendations.
        """
        prompt = f"""Analyze the following log entries and provide:
1. Root cause analysis
2. Impact assessment
3. Recommended fixes
4. Prevention strategies

Log Context:
{log_context}

{f"Additional Context: {additional_context}" if additional_context else ""}

Provide a comprehensive analysis with actionable recommendations."""

        return self.invoke(prompt)
