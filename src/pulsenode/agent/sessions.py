"""Session Storage and Management for PulseNode Agent."""

import json
from dataclasses import dataclass, field
from datetime import datetime, UTC
from pathlib import Path
from enum import Enum

from structlog import get_logger

logger = get_logger(__name__)


class SessionMode(str, Enum):
    """How sessions are created and managed for a channel."""

    TIME_BASED = "time_based"
    THREAD_BASED = "thread_based"


class TimeGranularity(str, Enum):
    """Time granularity for time-based sessions."""

    DAILY = "daily"
    WEEKLY = "weekly"


@dataclass
class Message:
    """A single message in a session."""

    role: str  # "user" or "agent"
    content: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class SessionConfig:
    """Configuration for session management."""

    session_mode: SessionMode = SessionMode.TIME_BASED
    time_granularity: TimeGranularity = TimeGranularity.WEEKLY
    min_messages_threshold: int = 5
    max_session_size_kb: int = 100
    can_access_other_agents: list[str] = field(default_factory=list)


@dataclass
class ChannelConfig:
    """Configuration for a specific channel."""

    channel_type: str  # "telegram", "email", etc.
    channel_identifier: str  # "chat_123", "email@example.com"
    session_config: SessionConfig = field(default_factory=SessionConfig)


@dataclass
class Session:
    """Represents a conversation session."""

    session_id: str  # "telegram:chat_123:2026-W07" or "email:address:thread_abc"
    agent_name: str  # Agent that owns this session
    channel_type: str  # "telegram", "email", etc.
    channel_identifier: str  # "chat_123", "email@example.com"
    week_number: str | None  # "2026-W07" for time-based, None for threads
    thread_id: str | None  # Thread ID for email, None for time-based
    messages: list[Message] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_activity: datetime = field(default_factory=lambda: datetime.now(UTC))

    # File system references
    session_file: Path | None = None
    agent_memory_path: Path | None = None
    channel_memory_path: Path | None = None
    index_file: Path | None = None
    archived_sessions_dir: Path | None = None

    def add_message(self, role: str, content: str) -> None:
        """Add a message to the session."""
        self.messages.append(Message(role=role, content=content))
        self.last_activity = datetime.now(UTC)

    def get_recent_messages(self, count: int = 10) -> list[Message]:
        """Get the most recent N messages."""
        return self.messages[-count:] if self.messages else []

    def get_context_summary(self, max_chars: int = 500) -> str:
        """Get a summary of older messages for context."""
        if len(self.messages) <= 10:
            return ""

        older_messages = self.messages[:-10]
        # Simple summary - in real implementation, use LLM to summarize
        summary_parts = []
        for msg in older_messages:
            if len("\n".join(summary_parts)) >= max_chars:
                break
            summary_parts.append(f"{msg.role}: {msg.content[:100]}...")

        return "\n".join(summary_parts)


@dataclass
class SessionIndexEntry:
    """Entry in the session index."""

    session_id: str
    summary: str
    message_count: int
    topics: list[str]
    start_date: str
    end_date: str
    file_size_kb: int


class SessionManager:
    """Manages sessions, memory, and file system operations."""

    def __init__(self, base_dir: Path):
        """Initialize session manager with base directory."""
        self.base_dir: Path = Path(base_dir)
        self.sessions: dict[str, Session] = {}  # session_id -> Session
        self._agent_memory_paths: dict[
            str, Path
        ] = {}  # agent_name -> agent_memory_path

    def _get_agent_dir(self, agent_name: str) -> Path:
        """Get the directory for an agent."""
        return self.base_dir / "agents" / agent_name

    def _get_channel_dir(
        self, agent_name: str, channel_type: str, channel_identifier: str
    ) -> Path:
        """Get the directory for a channel within an agent."""
        return (
            self._get_agent_dir(agent_name)
            / "channels"
            / channel_type
            / channel_identifier
        )

    def _get_sessions_dir(
        self, agent_name: str, channel_type: str, channel_identifier: str
    ) -> Path:
        """Get the sessions directory for a channel."""
        channel_dir = self._get_channel_dir(
            agent_name, channel_type, channel_identifier
        )
        return channel_dir / "sessions"

    def _ensure_agent_dir(self, agent_name: str) -> Path:
        """Ensure agent directory exists and return the agent memory path."""
        if agent_name in self._agent_memory_paths:
            return self._agent_memory_paths[agent_name]

        agent_dir = self._get_agent_dir(agent_name)
        agent_dir.mkdir(parents=True, exist_ok=True)

        agent_memory_file = agent_dir / "agent_memory.md"
        if not agent_memory_file.exists():
            agent_memory_file.write_text(f"# {agent_name} Agent Memory\n\n")

        self._agent_memory_paths[agent_name] = agent_memory_file
        return agent_memory_file

    async def get_or_create_session(
        self,
        agent_name: str,
        channel_type: str,
        channel_identifier: str,
        thread_id: str | None = None,
    ) -> Session:
        """Get existing session or create new one."""
        # Ensure agent directory exists
        self._ensure_agent_dir(agent_name)

        # Generate session ID
        if thread_id:
            session_id = f"{channel_type}:{channel_identifier}:thread_{thread_id}"
            week_number = None
        else:
            week_number = self._get_current_week()
            session_id = f"{channel_type}:{channel_identifier}:{week_number}"

        # Return existing session if in memory
        if session_id in self.sessions:
            return self.sessions[session_id]

        # Create session with file paths
        agent_dir = self._get_agent_dir(agent_name)
        channel_dir = self._get_channel_dir(
            agent_name, channel_type, channel_identifier
        )
        sessions_dir = channel_dir / "sessions"
        archived_dir = sessions_dir / "archived"

        for dir_path in [channel_dir, sessions_dir, archived_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)

        session = Session(
            session_id=session_id,
            agent_name=agent_name,
            channel_type=channel_type,
            channel_identifier=channel_identifier,
            week_number=week_number,
            thread_id=thread_id,
            session_file=sessions_dir / "current.md",
            agent_memory_path=agent_dir / "agent_memory.md",
            channel_memory_path=channel_dir / "long_term_memory.md",
            index_file=sessions_dir / "index.json",
            archived_sessions_dir=archived_dir,
        )

        # Load existing session if file exists
        if session.session_file and session.session_file.exists():
            await self._load_session_from_file(session)

        self.sessions[session_id] = session
        return session

    def _get_current_week(self) -> str:
        """Get current week in ISO format (e.g., '2026-W05')."""
        now = datetime.now(UTC)
        return now.strftime("%Y-W%U")

    async def _load_session_from_file(self, session: Session) -> None:
        """Load session data from markdown file."""
        if not session.session_file or not session.session_file.exists():
            return

        content = session.session_file.read_text()
        lines = content.split("\n")

        current_role = None
        for line in lines:
            line = line.strip()
            if not line:
                continue

            if line.startswith("**User**"):
                current_role = "user"
                content_part = line.replace("**User**:", "").strip()
                if content_part:
                    session.add_message("user", content_part)
            elif line.startswith("**Agent**"):
                current_role = "agent"
                content_part = line.replace("**Agent**:", "").strip()
                if content_part:
                    session.add_message("agent", content_part)
            elif current_role and not line.startswith("**"):
                # Continuation of previous message
                if session.messages:
                    session.messages[-1].content += "\n" + line

    async def save_session(self, session: Session) -> None:
        """Save session to markdown file."""
        if not session.session_file:
            return

        lines = [f"# Session: {session.session_id}"]
        lines.append(f"Started: {session.created_at.isoformat()}")
        lines.append(f"Last Activity: {session.last_activity.isoformat()}")
        lines.append("")

        for message in session.messages:
            if message.role == "user":
                lines.append(f"**User**: {message.content}")
            else:
                lines.append(f"**Agent**: {message.content}")

        session.session_file.write_text("\n".join(lines))

    async def archive_session(
        self, session: Session, summary: str, topics: list[str]
    ) -> None:
        """Archive a session and create new one."""
        if not session.archived_sessions_dir:
            return

        # Generate archive filename
        if session.week_number:
            archive_filename = f"{session.week_number}.md"
        else:
            archive_filename = f"thread_{session.thread_id}.md"

        archive_path = session.archived_sessions_dir / archive_filename

        # Move current file to archive
        if session.session_file and session.session_file.exists():
            session.session_file.rename(archive_path)

        # Update index
        await self._update_session_index(session, summary, topics, archive_path)

        # Clear messages from in-memory session
        session.messages.clear()

        # Clear session file reference (will be recreated when saved)
        if session.session_file and session.session_file.exists():
            session.session_file.unlink()

    async def _update_session_index(
        self, session: Session, summary: str, topics: list[str], archive_path: Path
    ) -> None:
        """Update the session index with archived session info."""
        if not session.index_file:
            return

        # Load existing index
        index_data = {}
        if session.index_file.exists():
            try:
                index_data = json.loads(session.index_file.read_text())
            except (json.JSONDecodeError, FileNotFoundError):
                pass

        # Calculate file size
        file_size_kb = (
            archive_path.stat().st_size // 1024 if archive_path.exists() else 0
        )

        # Create entry
        entry = SessionIndexEntry(
            session_id=session.session_id,
            summary=summary,
            message_count=len(session.messages),
            topics=topics,
            start_date=session.created_at.strftime("%Y-%m-%d"),
            end_date=session.last_activity.strftime("%Y-%m-%d"),
            file_size_kb=file_size_kb,
        )

        # Determine key for index
        if session.week_number:
            index_key = session.week_number
        else:
            index_key = f"thread_{session.thread_id}"

        # Add to index
        index_data[index_key] = {
            "session_id": entry.session_id,
            "summary": entry.summary,
            "message_count": entry.message_count,
            "topics": entry.topics,
            "start_date": entry.start_date,
            "end_date": entry.end_date,
            "file_size_kb": entry.file_size_kb,
        }

        # Save index
        session.index_file.write_text(json.dumps(index_data, indent=2))

    async def query_archived_sessions(
        self,
        agent_name: str,
        channel_type: str,
        channel_identifier: str,
        query: str,
        limit: int = 3,
    ) -> list[SessionIndexEntry]:
        """Search archived sessions by query."""
        sessions_dir = self._get_sessions_dir(
            agent_name, channel_type, channel_identifier
        )
        index_file = sessions_dir / "index.json"

        if not index_file.exists():
            return []

        try:
            index_data = json.loads(index_file.read_text())
        except (json.JSONDecodeError, FileNotFoundError):
            return []

        # TODO: Simple keyword search - in real implementation, use better search
        results = []
        query_lower = query.lower()

        for key, entry_data in index_data.items():
            if query_lower in entry_data["summary"].lower() or any(
                query_lower in topic.lower() for topic in entry_data["topics"]
            ):
                entry = SessionIndexEntry(
                    session_id=entry_data["session_id"],
                    summary=entry_data["summary"],
                    message_count=entry_data["message_count"],
                    topics=entry_data["topics"],
                    start_date=entry_data["start_date"],
                    end_date=entry_data["end_date"],
                    file_size_kb=entry_data["file_size_kb"],
                )
                results.append(entry)

                if len(results) >= limit:
                    break

        return results

    async def get_archived_session_content(
        self,
        agent_name: str,
        channel_type: str,
        channel_identifier: str,
        session_id: str,
    ) -> str:
        """Get the full content of an archived session."""
        sessions_dir = self._get_sessions_dir(
            agent_name, channel_type, channel_identifier
        )
        archived_dir = sessions_dir / "archived"

        # Determine filename
        if ":thread_" in session_id:
            thread_id = session_id.split(":thread_")[1]
            filename = f"thread_{thread_id}.md"
        else:
            week_part = session_id.split(":")[-1]
            filename = f"{week_part}.md"

        archive_path = archived_dir / filename

        if archive_path.exists():
            return archive_path.read_text()

        return ""

    async def update_agent_memory(
        self, agent_name: str, fact: str, importance: int = 3
    ) -> None:
        """Update agent memory with a new fact."""
        agent_memory_path = self._ensure_agent_dir(agent_name)

        if not agent_memory_path.exists():
            return

        content = agent_memory_path.read_text()

        importance_stars = "★" * importance
        new_fact = f"\n- [{importance_stars}] {fact}"

        agent_memory_path.write_text(content + new_fact)

    async def get_agent_memory(self, agent_name: str) -> str:
        """Get agent memory content."""
        agent_memory_path = self._ensure_agent_dir(agent_name)

        if agent_memory_path.exists():
            return agent_memory_path.read_text()

        return ""

    async def update_channel_memory(
        self, agent_name: str, channel_type: str, channel_identifier: str, fact: str
    ) -> None:
        """Update channel-specific long-term memory."""
        channel_dir = self._get_channel_dir(
            agent_name, channel_type, channel_identifier
        )
        channel_memory_file = channel_dir / "long_term_memory.md"

        channel_dir.mkdir(parents=True, exist_ok=True)

        if not channel_memory_file.exists():
            channel_memory_file.write_text(
                f"# {channel_type}:{channel_identifier} Long-term Memory\n\n"
            )

        content = channel_memory_file.read_text()
        new_fact = f"\n- {fact}"

        channel_memory_file.write_text(content + new_fact)

    async def get_channel_memory(
        self, agent_name: str, channel_type: str, channel_identifier: str
    ) -> str:
        """Get channel-specific long-term memory."""
        channel_dir = self._get_channel_dir(
            agent_name, channel_type, channel_identifier
        )
        channel_memory_file = channel_dir / "long_term_memory.md"

        if channel_memory_file.exists():
            return channel_memory_file.read_text()

        return ""
