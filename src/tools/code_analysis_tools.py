"""
Code Analysis Tools Module

Tools for analyzing error patterns and suggesting code fixes.
These tools can be used standalone or as part of the Coding Agent.
"""

import re

from strands import tool

from ..utils.config_loader import load_tools_config
from ..utils.logging_config import get_logger

logger = get_logger("tools.code_analysis")


class CodeAnalyzer:
    """
    Code analysis utility for error pattern recognition and fix suggestions.

    Can be used standalone or through the tool functions.

    Usage:
        analyzer = CodeAnalyzer()
        patterns = analyzer.analyze_patterns(log_context)
        severity = analyzer.assess_severity(patterns)
    """

    def __init__(self):
        """Initialize the code analyzer."""
        self._config = load_tools_config().get("code_analysis", {})
        self._severity_keywords = self._config.get("analysis", {}).get("severity_keywords", {})

    def analyze_patterns(self, log_context: str) -> dict:
        """
        Analyze log context to identify error patterns.

        Args:
            log_context: Formatted log entries as a string.

        Returns:
            Dictionary containing identified patterns and analysis.
        """
        patterns = {
            "error_types": [],
            "affected_services": set(),
            "timestamps": [],
            "stack_traces": [],
            "recurring_issues": [],
            "potential_causes": [],
        }

        lines = log_context.split("\n")
        error_counts: dict[str, int] = {}

        for line in lines:
            if not line.strip():
                continue

            # Extract service name (look for [service-name] pattern, but not status words)
            status_words = {"error", "warn", "warning", "info", "debug", "fatal", "critical"}
            for match in re.finditer(r"\[([a-z][\w-]*)\]", line, re.IGNORECASE):
                service_name = match.group(1)
                if service_name.lower() not in status_words:
                    patterns["affected_services"].add(service_name)
                    break  # Take first non-status match as service

            # Extract timestamp
            ts_match = re.search(r"\[(\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2})", line)
            if ts_match:
                patterns["timestamps"].append(ts_match.group(1))

            # Identify error types
            error_patterns = [
                (r"(NullPointerException)", "NullPointerException"),
                (r"(OutOfMemoryError)", "OutOfMemoryError"),
                (r"(ConnectionRefused|Connection refused)", "ConnectionRefused"),
                (r"(TimeoutException|Timeout|timed out)", "Timeout"),
                (r"(SQLException|database error)", "DatabaseError"),
                (r"(AuthenticationError|Unauthorized|401)", "AuthenticationError"),
                (r"(PermissionDenied|Forbidden|403)", "PermissionError"),
                (r"(FileNotFound|No such file)", "FileNotFoundError"),
                (r"(ValidationError|Invalid)", "ValidationError"),
                (r"(RateLimitExceeded|429|Too Many Requests)", "RateLimitError"),
            ]

            for pattern, error_type in error_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    if error_type not in patterns["error_types"]:
                        patterns["error_types"].append(error_type)
                    error_counts[error_type] = error_counts.get(error_type, 0) + 1

            # Check for stack traces
            if "at " in line and "(" in line and ")" in line:
                patterns["stack_traces"].append(line.strip())

        # Identify recurring issues (more than 3 occurrences)
        patterns["recurring_issues"] = [
            {"type": error, "count": count} for error, count in error_counts.items() if count >= 3
        ]

        # Convert set to list for JSON serialization
        patterns["affected_services"] = list(patterns["affected_services"])

        # Analyze potential causes
        patterns["potential_causes"] = self._identify_causes(patterns)

        return patterns

    def _identify_causes(self, patterns: dict) -> list[str]:
        """Identify potential root causes based on error patterns."""
        causes = []

        error_types = patterns.get("error_types", [])

        if "ConnectionRefused" in error_types or "Timeout" in error_types:
            causes.append("Network connectivity issues or service unavailability")

        if "OutOfMemoryError" in error_types:
            causes.append("Memory leak or insufficient heap allocation")

        if "NullPointerException" in error_types:
            causes.append("Null reference handling - missing null checks")

        if "DatabaseError" in error_types:
            causes.append("Database connection pool exhaustion or query issues")

        if "AuthenticationError" in error_types:
            causes.append("Expired or invalid credentials/tokens")

        if "RateLimitError" in error_types:
            causes.append("API rate limits exceeded - need backoff/retry logic")

        if "ValidationError" in error_types:
            causes.append("Input validation failures - check data format/schema")

        # Check for time patterns
        timestamps = patterns.get("timestamps", [])
        if len(timestamps) > 5:
            # Check if errors cluster around specific times
            causes.append("Possible time-based pattern - check scheduled jobs or traffic spikes")

        return causes

    def assess_severity(self, patterns: dict) -> str:
        """
        Assess the severity level based on error patterns.

        Args:
            patterns: Dictionary from analyze_patterns.

        Returns:
            Severity level: "critical", "high", "medium", or "low"
        """
        error_types = patterns.get("error_types", [])
        recurring = patterns.get("recurring_issues", [])

        # Check for critical errors
        critical_keywords = self._severity_keywords.get("critical", [])
        for error in error_types:
            for keyword in critical_keywords:
                if keyword.lower() in error.lower():
                    return "critical"

        # Check for high severity
        high_keywords = self._severity_keywords.get("high", [])
        for error in error_types:
            for keyword in high_keywords:
                if keyword.lower() in error.lower():
                    return "high"

        # High severity if many recurring issues
        if len(recurring) >= 3:
            return "high"

        # Medium if some errors identified
        if error_types:
            return "medium"

        return "low"

    def suggest_fixes(self, patterns: dict, service_name: str = "") -> list[dict]:
        """
        Generate fix suggestions based on identified patterns.

        Args:
            patterns: Dictionary from analyze_patterns.
            service_name: Name of the affected service.

        Returns:
            List of fix suggestions with code snippets where applicable.
        """
        suggestions = []
        error_types = patterns.get("error_types", [])

        # Fix suggestions for common error types
        fix_templates = {
            "NullPointerException": {
                "issue": "Null pointer reference",
                "suggestion": "Add null checks before accessing object properties",
                "code_snippet": """
# Python example
if obj is not None:
    result = obj.property
else:
    result = default_value

# Or use Optional with get()
result = obj.get('property', default_value) if obj else default_value
""",
                "prevention": "Use Optional types and null-safe operators",
            },
            "ConnectionRefused": {
                "issue": "Service connection failure",
                "suggestion": "Implement retry logic with exponential backoff",
                "code_snippet": """
import time
from functools import wraps

def retry_with_backoff(max_retries=3, base_delay=1):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except ConnectionError:
                    if attempt == max_retries - 1:
                        raise
                    delay = base_delay * (2 ** attempt)
                    time.sleep(delay)
        return wrapper
    return decorator
""",
                "prevention": "Use connection pools and health checks",
            },
            "Timeout": {
                "issue": "Request timeout",
                "suggestion": "Increase timeout values and add async processing",
                "code_snippet": """
import asyncio
from concurrent.futures import ThreadPoolExecutor

# Increase timeout
response = requests.get(url, timeout=30)  # Increased from default

# Or use async for long operations
async def fetch_with_timeout(url, timeout=30):
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=timeout) as response:
            return await response.json()
""",
                "prevention": "Monitor response times and set appropriate timeouts",
            },
            "OutOfMemoryError": {
                "issue": "Memory exhaustion",
                "suggestion": "Profile memory usage and optimize allocations",
                "code_snippet": """
# Use generators for large data
def process_large_file(filepath):
    with open(filepath) as f:
        for line in f:  # Process line by line
            yield process_line(line)

# Explicitly free memory
import gc
del large_object
gc.collect()
""",
                "prevention": "Set memory limits and implement pagination for large datasets",
            },
            "DatabaseError": {
                "issue": "Database operation failure",
                "suggestion": "Check connection pool settings and query optimization",
                "code_snippet": """
# Use connection pooling
from sqlalchemy import create_engine
from sqlalchemy.pool import QueuePool

engine = create_engine(
    db_url,
    poolclass=QueuePool,
    pool_size=5,
    max_overflow=10,
    pool_timeout=30
)

# Add query timeout
with engine.connect() as conn:
    conn.execute(text("SET statement_timeout = '30s'"))
""",
                "prevention": "Monitor connection pool metrics and slow queries",
            },
            "RateLimitError": {
                "issue": "API rate limit exceeded",
                "suggestion": "Implement rate limiting and request queuing",
                "code_snippet": """
from ratelimit import limits, sleep_and_retry

@sleep_and_retry
@limits(calls=100, period=60)  # 100 calls per minute
def call_api(endpoint):
    return requests.get(endpoint)

# Or use token bucket
class TokenBucket:
    def __init__(self, tokens, fill_rate):
        self.capacity = tokens
        self.tokens = tokens
        self.fill_rate = fill_rate
        self.last_time = time.time()
""",
                "prevention": "Cache responses and batch requests where possible",
            },
        }

        for error_type in error_types:
            if error_type in fix_templates:
                template = fix_templates[error_type]
                suggestions.append(
                    {
                        "error_type": error_type,
                        "service": service_name or "Unknown",
                        "severity": self.assess_severity({"error_types": [error_type]}),
                        **template,
                    }
                )

        # Add general suggestions based on causes
        for cause in patterns.get("potential_causes", []):
            if not any(s.get("issue", "") in cause for s in suggestions):
                suggestions.append(
                    {
                        "error_type": "General",
                        "service": service_name or "Unknown",
                        "severity": "medium",
                        "issue": cause,
                        "suggestion": "Review related code and configuration",
                        "prevention": "Add monitoring and alerting for this condition",
                    }
                )

        return suggestions


# Create a default analyzer instance
_default_analyzer: CodeAnalyzer | None = None


def _get_analyzer() -> CodeAnalyzer:
    """Get or create the default code analyzer."""
    global _default_analyzer
    if _default_analyzer is None:
        _default_analyzer = CodeAnalyzer()
    return _default_analyzer


@tool
def analyze_error_patterns(log_context: str) -> dict:
    """
    Analyze log entries to identify error patterns and potential issues.

    This tool parses formatted log entries and identifies:
    - Types of errors occurring
    - Affected services
    - Recurring issues
    - Potential root causes

    Args:
        log_context: Formatted log entries as a string.
                    Typically output from format_logs_for_analysis tool.

    Returns:
        Dictionary containing:
        - error_types: List of identified error types
        - affected_services: List of services with errors
        - recurring_issues: Issues occurring multiple times
        - potential_causes: Likely root causes
        - timestamps: Extracted timestamps

    Example:
        patterns = analyze_error_patterns(formatted_logs)
        print(f"Found errors: {patterns['error_types']}")
        print(f"Potential causes: {patterns['potential_causes']}")
    """
    analyzer = _get_analyzer()
    return analyzer.analyze_patterns(log_context)


@tool
def suggest_code_fix(
    error_patterns: dict,
    service_name: str = "",
) -> list[dict]:
    """
    Generate code fix suggestions based on identified error patterns.

    This tool provides actionable fix suggestions including code snippets
    for common error types identified in the log analysis.

    Args:
        error_patterns: Dictionary from analyze_error_patterns tool.
        service_name: Name of the affected service for context.

    Returns:
        List of fix suggestions, each containing:
        - error_type: Type of error addressed
        - service: Affected service name
        - severity: Severity level (critical/high/medium/low)
        - issue: Description of the issue
        - suggestion: Recommended fix approach
        - code_snippet: Example code for implementing the fix
        - prevention: How to prevent recurrence

    Example:
        patterns = analyze_error_patterns(logs)
        fixes = suggest_code_fix(patterns, service_name="payment-api")
        for fix in fixes:
            print(f"{fix['severity'].upper()}: {fix['issue']}")
            print(f"Fix: {fix['suggestion']}")
    """
    analyzer = _get_analyzer()
    return analyzer.suggest_fixes(error_patterns, service_name)


@tool
def assess_severity(error_patterns: dict) -> dict:
    """
    Assess the overall severity of identified error patterns.

    This tool evaluates the error patterns and returns a severity
    assessment that can be used for prioritization and alerting.

    Args:
        error_patterns: Dictionary from analyze_error_patterns tool.

    Returns:
        Dictionary containing:
        - severity: Overall severity level (critical/high/medium/low)
        - error_count: Total number of error types found
        - recurring_count: Number of recurring issues
        - recommendation: Recommended action based on severity

    Example:
        patterns = analyze_error_patterns(logs)
        assessment = assess_severity(patterns)
        if assessment['severity'] == 'critical':
            print("ALERT: Critical issues detected!")
    """
    analyzer = _get_analyzer()
    severity = analyzer.assess_severity(error_patterns)

    error_count = len(error_patterns.get("error_types", []))
    recurring_count = len(error_patterns.get("recurring_issues", []))

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
        "affected_services": error_patterns.get("affected_services", []),
        "recommendation": recommendations.get(severity, "Review and assess"),
    }
