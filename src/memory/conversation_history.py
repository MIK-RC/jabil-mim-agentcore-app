"""
Conversation History Module

Tracks and manages conversation history for the Orchestrator agent.
Provides utilities for storing, retrieving, and summarizing conversations.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from ..utils.logging_config import get_logger

logger = get_logger("memory.conversation")


class ConversationEntry(BaseModel):
    """A single entry in the conversation history."""

    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    role: str  # "user", "assistant", "system"
    content: str
    metadata: dict = Field(default_factory=dict)

    # Optional fields for tracking agent actions
    agent_name: str | None = None
    action_type: str | None = None
    tokens_used: int = 0


class ConversationHistory:
    """
    Manages conversation history for persistent memory.

    Provides functionality to:
    - Store conversation entries
    - Retrieve conversation context
    - Persist to file or S3
    - Summarize long conversations

    Usage:
        history = ConversationHistory(session_id="user-123")

        # Add entries
        history.add_user_message("Analyze errors in payment service")
        history.add_assistant_message("I'll analyze the payment service logs...")

        # Get context for prompts
        context = history.get_context(max_entries=10)

        # Persist
        history.save()
    """

    def __init__(
        self,
        session_id: str,
        storage_path: str | None = None,
        max_entries: int = 100,
        auto_save: bool = True,
    ):
        """
        Initialize conversation history.

        Args:
            session_id: Unique identifier for this conversation.
            storage_path: Path to store conversation file.
            max_entries: Maximum entries to keep in memory.
            auto_save: Whether to auto-save after each entry.
        """
        self._session_id = session_id
        self._max_entries = max_entries
        self._auto_save = auto_save

        # Determine storage path
        if storage_path:
            self._storage_path = Path(storage_path)
        else:
            self._storage_path = Path("./conversations") / f"{session_id}.json"

        # Initialize entries
        self._entries: list[ConversationEntry] = []

        # Load existing history if available
        self._load()

    @property
    def session_id(self) -> str:
        """Get the session ID."""
        return self._session_id

    @property
    def entries(self) -> list[ConversationEntry]:
        """Get all conversation entries."""
        return self._entries

    @property
    def entry_count(self) -> int:
        """Get the number of entries."""
        return len(self._entries)

    def add_entry(
        self,
        role: str,
        content: str,
        agent_name: str | None = None,
        action_type: str | None = None,
        metadata: dict | None = None,
        tokens_used: int = 0,
    ) -> None:
        """
        Add an entry to the conversation history.

        Args:
            role: The role (user, assistant, system).
            content: The message content.
            agent_name: Optional agent name for tracking.
            action_type: Optional action type.
            metadata: Optional additional metadata.
            tokens_used: Token count for this entry.
        """
        entry = ConversationEntry(
            role=role,
            content=content,
            agent_name=agent_name,
            action_type=action_type,
            metadata=metadata or {},
            tokens_used=tokens_used,
        )

        self._entries.append(entry)

        # Trim if exceeding max entries
        if len(self._entries) > self._max_entries:
            self._entries = self._entries[-self._max_entries :]

        if self._auto_save:
            self.save()

        logger.debug(f"Added {role} entry to conversation {self._session_id}")

    def add_user_message(self, content: str, metadata: dict | None = None) -> None:
        """Add a user message."""
        self.add_entry(role="user", content=content, metadata=metadata)

    def add_assistant_message(
        self,
        content: str,
        agent_name: str | None = None,
        action_type: str | None = None,
        metadata: dict | None = None,
        tokens_used: int = 0,
    ) -> None:
        """Add an assistant message."""
        self.add_entry(
            role="assistant",
            content=content,
            agent_name=agent_name,
            action_type=action_type,
            metadata=metadata,
            tokens_used=tokens_used,
        )

    def add_system_message(self, content: str, metadata: dict | None = None) -> None:
        """Add a system message."""
        self.add_entry(role="system", content=content, metadata=metadata)

    def get_context(
        self,
        max_entries: int | None = None,
        max_chars: int = 10000,
        include_system: bool = True,
    ) -> str:
        """
        Get conversation context as a formatted string.

        Args:
            max_entries: Maximum entries to include.
            max_chars: Maximum characters in the context.
            include_system: Whether to include system messages.

        Returns:
            Formatted conversation context.
        """
        entries = self._entries

        # Filter system messages if needed
        if not include_system:
            entries = [e for e in entries if e.role != "system"]

        # Limit entries
        if max_entries:
            entries = entries[-max_entries:]

        # Build context string
        lines = []
        total_chars = 0

        for entry in reversed(entries):
            role_label = {
                "user": "User",
                "assistant": "Assistant",
                "system": "System",
            }.get(entry.role, entry.role)

            if entry.agent_name:
                role_label = f"Assistant ({entry.agent_name})"

            line = f"[{entry.timestamp}] {role_label}: {entry.content}"

            if total_chars + len(line) > max_chars:
                break

            lines.insert(0, line)
            total_chars += len(line)

        return "\n\n".join(lines)

    def get_messages_for_llm(
        self,
        max_entries: int | None = None,
    ) -> list[dict]:
        """
        Get conversation entries in LLM message format.

        Args:
            max_entries: Maximum entries to include.

        Returns:
            List of message dictionaries with role and content.
        """
        entries = self._entries
        if max_entries:
            entries = entries[-max_entries:]

        return [{"role": entry.role, "content": entry.content} for entry in entries]

    def get_summary(self) -> str:
        """
        Get a summary of the conversation.

        Returns:
            Summary string.
        """
        if not self._entries:
            return "No conversation history."

        user_count = sum(1 for e in self._entries if e.role == "user")
        assistant_count = sum(1 for e in self._entries if e.role == "assistant")
        total_tokens = sum(e.tokens_used for e in self._entries)

        # Get unique agents involved
        agents = set(e.agent_name for e in self._entries if e.agent_name)

        lines = [
            "## Conversation Summary",
            f"- Session ID: {self._session_id}",
            f"- Total entries: {len(self._entries)}",
            f"- User messages: {user_count}",
            f"- Assistant messages: {assistant_count}",
            f"- Agents involved: {', '.join(agents) if agents else 'None'}",
            f"- Total tokens: {total_tokens}",
        ]

        if self._entries:
            first = self._entries[0]
            last = self._entries[-1]
            lines.append(f"- First entry: {first.timestamp}")
            lines.append(f"- Last entry: {last.timestamp}")

        return "\n".join(lines)

    def _load(self) -> None:
        """Load conversation history from storage."""
        if not self._storage_path.exists():
            return

        try:
            with open(self._storage_path) as f:
                data = json.load(f)

            self._entries = [ConversationEntry(**entry) for entry in data.get("entries", [])]

            logger.info(f"Loaded {len(self._entries)} entries from {self._storage_path}")

        except Exception as e:
            logger.warning(f"Failed to load conversation history: {e}")

    def save(self) -> None:
        """Save conversation history to storage."""
        try:
            # Ensure directory exists
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)

            data = {
                "session_id": self._session_id,
                "updated_at": datetime.now(UTC).isoformat(),
                "entries": [entry.model_dump() for entry in self._entries],
            }

            with open(self._storage_path, "w") as f:
                json.dump(data, f, indent=2)

            logger.debug(f"Saved conversation to {self._storage_path}")

        except Exception as e:
            logger.error(f"Failed to save conversation history: {e}")

    def clear(self, save: bool = True) -> None:
        """
        Clear the conversation history.

        Args:
            save: Whether to persist the clear operation.
        """
        self._entries = []

        if save:
            self.save()

        logger.info(f"Cleared conversation history for {self._session_id}")

    def export(self) -> dict:
        """
        Export the conversation history as a dictionary.

        Returns:
            Dictionary with session metadata and entries.
        """
        return {
            "session_id": self._session_id,
            "exported_at": datetime.now(UTC).isoformat(),
            "entry_count": len(self._entries),
            "entries": [entry.model_dump() for entry in self._entries],
        }
