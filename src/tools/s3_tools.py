"""
S3 Tools Module

Tools for storing analysis reports and logs to Amazon S3.
These tools can be used standalone or as part of the S3 Agent.
"""

import os
from datetime import UTC, datetime

import boto3
from botocore.exceptions import ClientError
from strands import tool

from ..utils.config_loader import load_settings
from ..utils.logging_config import get_logger

logger = get_logger("tools.s3")


class S3Client:
    """
    S3 client for storing analysis reports.

    Can be used standalone or through the tool functions.

    Usage:
        # Standalone usage
        client = S3Client()
        result = client.upload_report("service-name", "# Report content...")

        # With custom bucket
        client = S3Client(bucket="my-custom-bucket")
    """

    def __init__(
        self,
        bucket: str | None = None,
        region: str | None = None,
    ):
        """
        Initialize the S3 client.

        Args:
            bucket: S3 bucket name. Defaults to S3_REPORTS_BUCKET env var.
            region: AWS region. Defaults to config.
        """
        # Ensure environment variables are loaded from .env file (for local development)
        # In deployed environments, this is a no-op and boto3 uses IAM role credentials
        from dotenv import load_dotenv

        load_dotenv()

        settings = load_settings()

        self._bucket = bucket or os.environ.get("S3_REPORTS_BUCKET")
        self._region = region or settings.get("aws", {}).get("region", "us-east-1")

        if not self._bucket:
            logger.warning("S3 reports bucket not configured")

        # Use boto3 default credential chain:
        # - Local: picks up AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY from environment
        # - Deployed: automatically uses IAM role credentials
        self._client = boto3.client("s3", region_name=self._region)

    def upload_report(
        self,
        service_name: str,
        content: str,
        timestamp: str | None = None,
    ) -> dict:
        """
        Upload a service report to S3.

        Args:
            service_name: Name of the service.
            content: Markdown content of the report.
            timestamp: Optional timestamp. Defaults to current time.

        Returns:
            Dict with upload details or error.
        """
        if not self._bucket:
            logger.error("S3 reports bucket not configured")
            return {"success": False, "error": "S3 reports bucket not configured"}

        if not timestamp:
            timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%SZ")

        key = f"{service_name}/{timestamp}.md"

        try:
            self._client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=content.encode("utf-8"),
                ContentType="text/markdown",
            )

            s3_uri = f"s3://{self._bucket}/{key}"
            logger.info(f"Uploaded report: {s3_uri}")

            return {
                "success": True,
                "bucket": self._bucket,
                "key": key,
                "s3_uri": s3_uri,
            }

        except ClientError as e:
            logger.error(f"Failed to upload report: {e}")
            return {"success": False, "error": str(e)}

    def upload_summary(
        self,
        content: str,
        timestamp: str | None = None,
    ) -> dict:
        """
        Upload a summary report to the summaries folder.

        Args:
            content: Markdown content of the summary.
            timestamp: Optional timestamp. Defaults to current time.

        Returns:
            Dict with upload details or error.
        """
        if not self._bucket:
            logger.error("S3 reports bucket not configured")
            return {"success": False, "error": "S3 reports bucket not configured"}

        now = datetime.now(UTC)
        if not timestamp:
            timestamp = now.strftime("%Y-%m-%dT%H-%M-%SZ")

        date_folder = now.strftime("%Y-%m-%d")
        key = f"summaries/{date_folder}/{timestamp}.md"

        try:
            self._client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=content.encode("utf-8"),
                ContentType="text/markdown",
            )

            s3_uri = f"s3://{self._bucket}/{key}"
            logger.info(f"Uploaded summary: {s3_uri}")

            return {
                "success": True,
                "bucket": self._bucket,
                "key": key,
                "s3_uri": s3_uri,
            }

        except ClientError as e:
            logger.error(f"Failed to upload summary: {e}")
            return {"success": False, "error": str(e)}


# Create a default client instance for tool functions
_default_client: S3Client | None = None


def _get_client() -> S3Client:
    """Get or create the default S3 client."""
    global _default_client
    if _default_client is None:
        _default_client = S3Client()
    return _default_client


@tool
def upload_service_report(
    service_name: str,
    content: str,
) -> dict:
    """
    Upload a service analysis report to S3.

    Stores the report in the format: s3://bucket/{service_name}/{timestamp}.md

    Args:
        service_name: Name of the service being reported on.
        content: Markdown content of the report.

    Returns:
        Dictionary with upload result including S3 URI or error details.

    Example:
        result = upload_service_report(
            service_name="payment-service",
            content="# Error Report\\n\\n..."
        )
    """
    client = _get_client()
    return client.upload_report(service_name, content)


@tool
def upload_summary_report(content: str) -> dict:
    """
    Upload a summary report to the summaries folder in S3.

    Stores the report in: s3://bucket/summaries/{date}/{timestamp}.md

    Args:
        content: Markdown content of the summary report.

    Returns:
        Dictionary with upload result including S3 URI or error details.

    Example:
        result = upload_summary_report("# Daily Summary\\n\\n...")
    """
    client = _get_client()
    return client.upload_summary(content)
