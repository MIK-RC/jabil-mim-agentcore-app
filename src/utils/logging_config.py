"""
Logging Configuration Module

Provides standardized logging setup for the AIOps Multi-Agent System.
Supports both standard and JSON formatting for production use.
"""

import json
import logging
import sys
from datetime import datetime

from .config_loader import load_settings


class JSONFormatter(logging.Formatter):
    """
    JSON formatter for structured logging in production environments.

    Output format:
    {
        "timestamp": "2024-01-15T10:30:00.000Z",
        "level": "INFO",
        "logger": "src.agents.orchestrator",
        "message": "Agent initialized",
        "extra": {...}
    }
    """

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "extra": None,
        }

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields
        extra_fields = {
            key: value
            for key, value in record.__dict__.items()
            if key
            not in (
                "name",
                "msg",
                "args",
                "created",
                "filename",
                "funcName",
                "levelname",
                "levelno",
                "lineno",
                "module",
                "msecs",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "stack_info",
                "exc_info",
                "exc_text",
                "thread",
                "threadName",
                "message",
                "taskName",
            )
        }
        if extra_fields:
            log_data["extra"] = extra_fields

        return json.dumps(log_data)


class AgentLoggerAdapter(logging.LoggerAdapter):
    """
    Logger adapter that adds agent context to log messages.

    Usage:
        logger = get_logger("orchestrator", agent_id="agent-123")
        logger.info("Processing request", extra={"user_id": "user-456"})
    """

    def process(self, msg: str, kwargs: dict) -> tuple[str, dict]:
        # Merge extra context
        extra = kwargs.get("extra", {})
        extra.update(self.extra)
        kwargs["extra"] = extra
        return msg, kwargs


def setup_logging(
    level: str | None = None,
    json_format: bool | None = None,
    log_format: str | None = None,
) -> None:
    """
    Set up logging configuration for the application.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
               Defaults to config setting.
        json_format: Whether to use JSON formatting. Defaults to config setting.
        log_format: Custom log format string. Defaults to config setting.

    Usage:
        from src.utils import setup_logging

        # Use config defaults
        setup_logging()

        # Override with custom settings
        setup_logging(level="DEBUG", json_format=True)
    """
    settings = load_settings()
    logging_config = settings.get("logging", {})

    # Resolve settings (args override config)
    effective_level = level or logging_config.get("level", "INFO")
    effective_json = (
        json_format if json_format is not None else logging_config.get("json_format", False)
    )
    effective_format = log_format or logging_config.get(
        "format", "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Get the root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, effective_level.upper()))

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, effective_level.upper()))

    # Set formatter based on json_format flag
    if effective_json:
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(effective_format)

    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Reduce noise from third-party libraries
    logging.getLogger("boto3").setLevel(logging.WARNING)
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def get_logger(
    name: str,
    agent_id: str | None = None,
    **extra_context: str,
) -> logging.Logger | AgentLoggerAdapter:
    """
    Get a logger instance with optional agent context.

    Args:
        name: Logger name (typically module or agent name)
        agent_id: Optional agent identifier for context
        **extra_context: Additional context fields to include in all logs

    Returns:
        Logger or LoggerAdapter with context

    Usage:
        # Simple logger
        logger = get_logger("src.tools.datadog")
        logger.info("Querying logs")

        # Logger with agent context
        logger = get_logger("orchestrator", agent_id="orch-123", session_id="sess-456")
        logger.info("Processing user request")
    """
    # Ensure name has proper prefix
    if not name.startswith("src.") and not name.startswith("aiops."):
        name = f"src.{name}"

    logger = logging.getLogger(name)

    # If context is provided, wrap with adapter
    if agent_id or extra_context:
        context = {"agent_id": agent_id} if agent_id else {}
        context.update(extra_context)
        return AgentLoggerAdapter(logger, context)

    return logger
