"""
Session Manager Module

Factory and utilities for creating session managers.
Supports S3 and file-based storage backends.
"""

import os
from enum import Enum

from strands.session import FileSessionManager, S3SessionManager, SessionManager

from ..utils.config_loader import load_settings
from ..utils.logging_config import get_logger

logger = get_logger("memory.session")


class StorageBackend(Enum):
    """Supported storage backends for session management."""

    S3 = "s3"
    FILE = "file"


class SessionManagerFactory:
    """
    Factory for creating session managers.

    Creates the appropriate session manager based on configuration
    or explicit parameters. Supports S3 and file-based storage.

    Usage:
        # Using config defaults
        manager = SessionManagerFactory.create("user-session-123")

        # Explicit S3 storage
        manager = SessionManagerFactory.create(
            session_id="user-123",
            backend=StorageBackend.S3,
            bucket="my-bucket"
        )

        # File-based storage
        manager = SessionManagerFactory.create(
            session_id="user-123",
            backend=StorageBackend.FILE,
            storage_dir="./sessions"
        )
    """

    @staticmethod
    def create(
        session_id: str,
        backend: StorageBackend | None = None,
        bucket: str | None = None,
        prefix: str | None = None,
        storage_dir: str | None = None,
        region: str | None = None,
    ) -> SessionManager:
        """
        Create a session manager.

        Args:
            session_id: Unique identifier for the session.
            backend: Storage backend (S3 or FILE). Defaults based on config/env.
            bucket: S3 bucket name (required for S3 backend).
            prefix: S3 key prefix (optional for S3 backend).
            storage_dir: Local directory (required for FILE backend).
            region: AWS region for S3 (optional).

        Returns:
            Configured SessionManager instance.
        """
        settings = load_settings()
        session_config = settings.get("session", {})
        aws_config = settings.get("aws", {})

        # Determine backend
        if backend is None:
            # Check environment variable
            env_backend = os.environ.get("AIOPS_SESSION_BACKEND", "").lower()
            if env_backend == "s3":
                backend = StorageBackend.S3
            elif env_backend == "file":
                backend = StorageBackend.FILE
            else:
                # Default to S3 if bucket is configured, otherwise file
                if session_config.get("bucket") or bucket:
                    backend = StorageBackend.S3
                else:
                    backend = StorageBackend.FILE

        if backend == StorageBackend.S3:
            return SessionManagerFactory._create_s3_manager(
                session_id=session_id,
                bucket=bucket or session_config.get("bucket", "aiops-agent-sessions"),
                prefix=prefix or session_config.get("prefix", "sessions/"),
                region=region or aws_config.get("region", "us-east-1"),
            )
        else:
            return SessionManagerFactory._create_file_manager(
                session_id=session_id,
                storage_dir=storage_dir or "./sessions",
            )

    @staticmethod
    def _create_s3_manager(
        session_id: str,
        bucket: str,
        prefix: str,
        region: str,
    ) -> S3SessionManager:
        """Create an S3-based session manager."""
        logger.info(f"Creating S3 session manager: s3://{bucket}/{prefix}{session_id}")

        return S3SessionManager(
            session_id=session_id,
            bucket=bucket,
            prefix=prefix,
            region_name=region,
        )

    @staticmethod
    def _create_file_manager(
        session_id: str,
        storage_dir: str,
    ) -> FileSessionManager:
        """Create a file-based session manager."""
        # Ensure directory exists
        os.makedirs(storage_dir, exist_ok=True)

        logger.info(f"Creating file session manager: {storage_dir}/{session_id}")

        return FileSessionManager(
            session_id=session_id,
            storage_dir=storage_dir,
        )


def get_session_manager(
    session_id: str,
    use_s3: bool | None = None,
    **kwargs,
) -> SessionManager:
    """
    Convenience function to get a session manager.

    Args:
        session_id: Unique identifier for the session.
        use_s3: Whether to use S3 storage. If None, auto-detected.
        **kwargs: Additional arguments passed to SessionManagerFactory.

    Returns:
        Configured SessionManager instance.

    Usage:
        # Auto-detect backend
        manager = get_session_manager("user-123")

        # Force S3
        manager = get_session_manager("user-123", use_s3=True, bucket="my-bucket")

        # Force file-based
        manager = get_session_manager("user-123", use_s3=False)
    """
    backend = None
    if use_s3 is True:
        backend = StorageBackend.S3
    elif use_s3 is False:
        backend = StorageBackend.FILE

    return SessionManagerFactory.create(
        session_id=session_id,
        backend=backend,
        **kwargs,
    )
