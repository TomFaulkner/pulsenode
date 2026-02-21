"""Memory Management System for PulseNode Agent.

Handles three-tier memory architecture:
- Agent Memory: Cross-channel knowledge for an agent
- Channel Memory: Long-term facts about specific channels
- Session Memory: Current conversation history and archives
"""

from datetime import datetime, UTC

from structlog import get_logger

from pulsenode.agent.sessions import (
    SessionManager,
    Session,
    SessionConfig,
    TimeGranularity,
    SessionMode,
)
from pulsenode.agent.agent_config import AgentConfigManager

logger = get_logger(__name__)


class MemoryManager:
    """High-level memory management for agents."""

    def __init__(
        self, session_manager: SessionManager, config_manager: AgentConfigManager
    ):
        """Initialize memory manager with session manager and config manager."""
        self.session_manager = session_manager
        self.config_manager = config_manager

    async def get_context_for_llm(
        self,
        session: Session,
        query: str | None = None,
        max_agent_memory_chars: int = 1000,
        max_channel_memory_chars: int = 800,
        max_session_summary_chars: int = 500,
    ) -> str:
        """Get full context for LLM prompt including all memory tiers."""
        context_parts = []

        # Agent Memory (cross-channel knowledge)
        agent_memory = await self.session_manager.get_agent_memory(session.agent_name)
        if agent_memory.strip():
            agent_context = self._limit_memory_section(
                agent_memory, max_agent_memory_chars
            )
            context_parts.append(f"## Agent Knowledge\n{agent_context}")

        # Channel Memory (channel-specific facts)
        channel_memory = await self.session_manager.get_channel_memory(
            session.agent_name, session.channel_type, session.channel_identifier
        )
        if channel_memory.strip():
            channel_context = self._limit_memory_section(
                channel_memory, max_channel_memory_chars
            )
            context_parts.append(f"## Channel Context\n{channel_context}")

        # Session Summary (older messages in current session)
        session_summary = session.get_context_summary(max_session_summary_chars)
        if session_summary.strip():
            context_parts.append(f"## Recent History Summary\n{session_summary}")

        # Recent Messages (full recent messages)
        recent_messages = session.get_recent_messages(10)
        if recent_messages:
            messages_text = "\n".join(
                [f"{msg.role}: {msg.content}" for msg in recent_messages]
            )
            context_parts.append(f"## Recent Messages\n{messages_text}")

        # If query provided, try to find relevant archived sessions
        if query:
            relevant_archived = await self.session_manager.query_archived_sessions(
                session.agent_name,
                session.channel_type,
                session.channel_identifier,
                query,
            )
            if relevant_archived:
                archive_context = self._format_archive_context(relevant_archived)
                context_parts.append(
                    f"## Relevant Past Conversations\n{archive_context}"
                )

        return "\n\n".join(context_parts)

    def _limit_memory_section(self, content: str, max_chars: int) -> str:
        """Limit memory section to max characters, preserving structure."""
        if len(content) <= max_chars:
            return content

        # Simple truncation for now - could be smarter with markdown parsing
        return content[:max_chars] + "\n... (truncated)"

    def _format_archive_context(self, archived_sessions: list) -> str:
        """Format archived session references for context."""
        if not archived_sessions:
            return ""

        lines = []
        for i, entry in enumerate(archived_sessions, 1):
            lines.append(
                f"{i}. **{entry.session_id}** ({entry.start_date} - {entry.end_date})"
            )
            lines.append(f"   Summary: {entry.summary}")
            lines.append(f"   Topics: {', '.join(entry.topics)}")

        return "\n".join(lines)

    async def update_long_term_memory(
        self,
        session: Session,
        fact: str,
        importance: int = 3,
        memory_type: str = "agent",  # "agent" or "channel"
    ) -> None:
        """Update long-term memory with a new fact."""
        logger.info(
            "updating_long_term_memory",
            session_id=session.session_id,
            fact=fact[:100] + "..." if len(fact) > 100 else fact,
            importance=importance,
            memory_type=memory_type,
        )

        if memory_type == "agent":
            await self.session_manager.update_agent_memory(
                session.agent_name, fact, importance
            )
        elif memory_type == "channel":
            await self.session_manager.update_channel_memory(
                session.agent_name,
                session.channel_type,
                session.channel_identifier,
                fact,
            )
        else:
            raise ValueError(f"Invalid memory_type: {memory_type}")

    async def should_archive_session(self, session: Session) -> tuple[bool, str]:
        """Check if session should be archived and why."""
        now = datetime.now(UTC)
        config = await self._get_session_config(session)

        # Check time-based rollover
        if config.session_mode == SessionMode.TIME_BASED:
            current_week = self.session_manager._get_current_week()
            if session.week_number and session.week_number != current_week:
                return True, f"Week boundary: {session.week_number} -> {current_week}"

            if config.time_granularity == TimeGranularity.DAILY:
                current_day = now.strftime("%Y-%m-%d")
                session_day = session.created_at.strftime("%Y-%m-%d")
                if session_day != current_day:
                    return True, f"Day boundary: {session_day} -> {current_day}"

        # Check size-based archive
        if session.session_file and session.session_file.exists():
            file_size_kb = session.session_file.stat().st_size // 1024
            if file_size_kb > config.max_session_size_kb:
                return (
                    True,
                    f"Size limit: {file_size_kb}KB > {config.max_session_size_kb}KB",
                )

        # Check message count
        if (
            len(session.messages) > config.min_messages_threshold * 5
        ):  # Archive at 5x threshold
            return True, f"Message count: {len(session.messages)} messages"

        return False, ""

    async def _get_session_config(self, session: Session) -> SessionConfig:
        """Get session configuration for a session."""
        agent_config = await self.config_manager.load_agent_config(session.agent_name)
        session_config = agent_config.session_config

        channel_id = f"{session.channel_type}:{session.channel_identifier}"
        for ch in agent_config.channels:
            if f"{ch.type}:{ch.identifier}" == channel_id:
                return session_config

        return session_config

    async def archive_and_create_new_session(
        self, session: Session, summary: str = "", topics: list[str] | None = None
    ) -> Session:
        """Archive current session and create new one."""
        logger.info("archiving_session", session_id=session.session_id)

        # Generate summary if not provided
        if not summary:
            summary = await self._generate_session_summary(session)

        if topics is None:
            topics = await self._extract_topics(session)

        # Archive current session
        await self.session_manager.archive_session(session, summary, topics)

        # Create new session with same channel but new week
        new_session = await self.session_manager.get_or_create_session(
            session.agent_name,
            session.channel_type,
            session.channel_identifier,
            session.thread_id,  # Preserve thread ID for email
        )

        # Add context from archived session
        context_message = (
            f"Previous session ({session.session_id}) archived. "
            f"Summary: {summary}. "
            f"Key topics: {', '.join(topics)}."
        )
        new_session.add_message("system", context_message)

        return new_session

    async def _generate_session_summary(self, session: Session) -> str:
        """Generate a summary of the session."""
        # Simple summary - in real implementation, use LLM
        if len(session.messages) == 0:
            return "Empty session"

        # Use first and last few messages for context
        first_msg = session.messages[0].content if session.messages else ""
        last_msg = session.messages[-1].content if session.messages else ""

        return f"Session with {len(session.messages)} messages. Started about '{first_msg[:50]}...', ended about '{last_msg[:50]}...'"

    async def _extract_topics(self, session: Session) -> list[str]:
        """Extract topics from session messages."""
        # Simple keyword extraction - in real implementation, use LLM
        all_content = " ".join([msg.content.lower() for msg in session.messages])

        # Simple topic detection
        common_topics = [
            "python",
            "async",
            "database",
            "api",
            "email",
            "telegram",
            "project",
            "deadline",
        ]
        topics = []

        for topic in common_topics:
            if topic in all_content and topic not in topics:
                topics.append(topic)

        return topics if topics else ["general"]


class MemoryTools:
    """Tools for LLM to manage memory."""

    def __init__(self, memory_manager: MemoryManager):
        """Initialize memory tools."""
        self.memory_manager = memory_manager

    async def update_agent_memory(
        self, session: Session, fact: str, importance: int = 3
    ) -> str:
        """Update agent memory with a new fact."""
        await self.memory_manager.update_long_term_memory(
            session, fact, importance, "agent"
        )
        return f"Added to agent memory: {fact}"

    async def update_channel_memory(self, session: Session, fact: str) -> str:
        """Update channel memory with a new fact."""
        await self.memory_manager.update_long_term_memory(session, fact, 3, "channel")
        return f"Added to channel memory: {fact}"

    async def query_archived_sessions(
        self, session: Session, query: str, limit: int = 3
    ) -> str:
        """Search archived sessions."""
        results = await self.memory_manager.session_manager.query_archived_sessions(
            session.agent_name,
            session.channel_type,
            session.channel_identifier,
            query,
            limit,
        )

        if not results:
            return "No relevant archived sessions found."

        response = f"Found {len(results)} relevant archived session(s):\n\n"
        for i, entry in enumerate(results, 1):
            response += f"{i}. {entry.session_id}\n"
            response += f"   Summary: {entry.summary}\n"
            response += f"   Topics: {', '.join(entry.topics)}\n"
            response += f"   Date range: {entry.start_date} to {entry.end_date}\n\n"

        return response

    async def get_archived_session(self, session: Session, session_id: str) -> str:
        """Get full content of an archived session."""
        content = (
            await self.memory_manager.session_manager.get_archived_session_content(
                session.agent_name,
                session.channel_type,
                session.channel_identifier,
                session_id,
            )
        )

        if not content:
            return f"Archived session {session_id} not found."

        return content

    async def get_memory_status(self, session: Session) -> str:
        """Get status of current memory state."""
        should_archive, reason = await self.memory_manager.should_archive_session(
            session
        )

        status = [
            f"Session ID: {session.session_id}",
            f"Messages: {len(session.messages)}",
            f"Created: {session.created_at.strftime('%Y-%m-%d %H:%M')}",
            f"Last Activity: {session.last_activity.strftime('%Y-%m-%d %H:%M')}",
            f"Should Archive: {should_archive}",
        ]

        if should_archive:
            status.append(f"Archive Reason: {reason}")

        # Get file sizes
        if session.session_file and session.session_file.exists():
            size_kb = session.session_file.stat().st_size // 1024
            status.append(f"Session File Size: {size_kb}KB")

        # Get memory sizes
        agent_memory = await self.memory_manager.session_manager.get_agent_memory(
            session.agent_name
        )
        channel_memory = await self.memory_manager.session_manager.get_channel_memory(
            session.agent_name, session.channel_type, session.channel_identifier
        )

        status.append(f"Agent Memory: {len(agent_memory)} chars")
        status.append(f"Channel Memory: {len(channel_memory)} chars")

        return "\n".join(status)
