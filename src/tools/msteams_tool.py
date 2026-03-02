"""
MS Teams Tools Module

Tool for sending proactive workflow summaries to an MS Teams channel
via Power Automate webhook.
"""

# import logging  # TODO: Add logging
import requests
from strands import tool

from ..utils.config_loader import load_settings
from ..utils.logging_config import get_logger

logger = get_logger("tools.msteams")


class MSTeamsClient:
    """
    MS Teams client for sending notifications via Power Automate.

    Usage:
        client = MSTeamsClient()
        result = client.send_notification("proactive-workflow", "summary text")
    """

    def __init__(self):
        settings = load_settings()
        msteams_config = settings.get("msteams", {})

        self._webhook_url = msteams_config.get("webhook_url")
        self._timeout = msteams_config.get("timeout_seconds", 10)
        self.emails_list = self.get_emails_list()

        if not self._webhook_url:
            logger.warning("MS Teams webhook URL not configured")

    def get_emails_list(self):
        # Placeholder import – assume this comes from another module
        # Example: from ..utils.notification_recipients import MS_TEAMS_EMAILS
        ms_teams_email: list[str] = ["muhammad.ibrahim@royalcyber.com"]  # <-- placeholder
        return ms_teams_email

    def _build_schema(self) -> list[dict]:
        """
        Build schema dynamically from configured email list.
        """
        schema = []

        for idx, email in enumerate(self.emails_list, start=1):
            schema.append(
                {
                    "field": f"emailid_{idx}",
                    "type": "string",
                    "label": "Email Id",
                    "value": email,
                }
            )

        return schema

    def send_notification(self, agent_id: str, message: str) -> dict:
        """
        Send a notification to MS Teams via Power Automate.

        Args:
            agent_id: Identifier of the calling agent/workflow
            message: Message body (summary report)

        Returns:
            Dict with success status or error details.
        """
        if not self._webhook_url:
            error = "MS Teams webhook URL not configured"
            logger.error(error)
            return {"success": False, "error": error}

        payload = {
            "agent_id": agent_id,
            "message": message,
            "schema": self._build_schema(),
        }

        try:
            response = requests.post(
                self._webhook_url,
                json=payload,
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            logger.exception("Failed to send MS Teams notification")
            return {"success": False, "error": str(exc)}

        success = 200 <= response.status_code < 300

        if success:
            logger.info("MS Teams notification accepted by Power Automate")
        else:
            logger.error(
                "MS Teams notification rejected. status=%s response=%s",
                response.status_code,
                response.text,
            )

        return {
            "success": success,
            "status_code": response.status_code,
            "response": response.text,
        }


_default_client: MSTeamsClient | None = None


def _get_client() -> MSTeamsClient:
    global _default_client
    if _default_client is None:
        _default_client = MSTeamsClient()
    return _default_client


@tool
def send_msteams_notification(
    agent_id: str,
    message: str,
) -> dict:
    """
    Send a notification to an MS Teams channel via Power Automate.

    Args:
        agent_id: Identifier of the calling agent/workflow.
        message: Message body (typically a summary report).

    Returns:
        Dictionary with success or error details.

    Example:
        result = send_msteams_notification(
            agent_id="proactive-workflow",
            message="# Summary\\n..."
        )
    """
    client = _get_client()
    return client.send_notification(agent_id, message)
