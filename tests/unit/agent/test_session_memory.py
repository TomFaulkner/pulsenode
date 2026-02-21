#!/usr/bin/env python3

import asyncio
import sys
import os
import tempfile
from pathlib import Path

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from pulsenode.agent.sessions import SessionManager
from pulsenode.agent.memory import MemoryManager, MemoryTools
from pulsenode.agent.agent_config import AgentConfigManager


async def test_session_creation():
    """Test basic session creation and management."""
    print("Testing session creation...")

    # Create temporary directory for tests
    with tempfile.TemporaryDirectory() as temp_dir:
        base_dir = Path(temp_dir)
        session_manager = SessionManager(base_dir)

        # Create a session
        session = await session_manager.get_or_create_session(
            "test_agent", "telegram", "chat_123"
        )

        assert session.agent_name == "test_agent"
        assert session.channel_type == "telegram"
        assert session.channel_identifier == "chat_123"
        # Check that session_id has the expected pattern
        assert session.session_id.startswith("telegram:chat_123:")
        assert "W" in session.session_id  # Week indicator

        # Add messages
        session.add_message("user", "Hello!")
        session.add_message("agent", "Hi there!")

        # Save session
        await session_manager.save_session(session)

        # Verify file was created
        assert session.session_file and session.session_file.exists()

        # Load session again (should get same session)
        session2 = await session_manager.get_or_create_session(
            "test_agent", "telegram", "chat_123"
        )

        assert len(session2.messages) == 2
        assert session2.messages[0].content == "Hello!"
        assert session2.messages[1].content == "Hi there!"

        print("✓ Session creation and persistence works")


async def test_thread_sessions():
    """Test thread-based session creation."""
    print("Testing thread sessions...")

    with tempfile.TemporaryDirectory() as temp_dir:
        base_dir = Path(temp_dir)
        session_manager = SessionManager(base_dir)

        # Create thread-based session
        session = await session_manager.get_or_create_session(
            "test_agent", "email", "user@example.com", "thread_abc123"
        )

        assert session.session_id == "email:user@example.com:thread_thread_abc123"
        assert session.thread_id == "thread_abc123"
        assert session.week_number is None

        print("✓ Thread sessions work correctly")


async def test_session_archiving():
    """Test session archiving functionality."""
    print("Testing session archiving...")

    with tempfile.TemporaryDirectory() as temp_dir:
        base_dir = Path(temp_dir)
        session_manager = SessionManager(base_dir)
        config_manager = AgentConfigManager(base_dir)
        memory_manager = MemoryManager(session_manager, config_manager)

        # Create session and add messages
        session = await session_manager.get_or_create_session(
            "test_agent", "telegram", "chat_123"
        )

        for i in range(10):
            session.add_message("user", f"User message {i}")
            session.add_message("agent", f"Agent response {i}")

        await session_manager.save_session(session)

        # Archive session
        new_session = await memory_manager.archive_and_create_new_session(
            session, "Test session", ["python", "testing"]
        )

        # Verify old session was archived
        assert session.archived_sessions_dir and session.archived_sessions_dir.exists()

        # Verify index was created
        assert session.index_file and session.index_file.exists()

        # Verify new session has context
        assert len(new_session.messages) == 1
        assert "Previous session" in new_session.messages[0].content

        print("✓ Session archiving works correctly")


async def test_memory_context():
    """Test memory context generation."""
    print("Testing memory context generation...")

    with tempfile.TemporaryDirectory() as temp_dir:
        base_dir = Path(temp_dir)
        session_manager = SessionManager(base_dir)
        config_manager = AgentConfigManager(base_dir)
        memory_manager = MemoryManager(session_manager, config_manager)

        # Create session with some memory
        session = await session_manager.get_or_create_session(
            "test_agent", "telegram", "chat_123"
        )

        # Add agent memory
        await session_manager.update_agent_memory(
            "test_agent", "User prefers Python over JavaScript", 4
        )

        # Add channel memory
        await session_manager.update_channel_memory(
            "test_agent", "telegram", "chat_123", "This chat is about async programming"
        )

        # Add some messages
        for i in range(5):
            session.add_message("user", f"How do I handle async {i}?")
            session.add_message("agent", f"Use asyncio for async {i}")

        # Get context
        context = await memory_manager.get_context_for_llm(session, "How about async?")

        assert "Agent Knowledge" in context
        assert "Channel Context" in context
        assert "Recent Messages" in context
        assert "async" in context.lower()

        print("✓ Memory context generation works correctly")


async def test_agent_config():
    """Test agent configuration management."""
    print("Testing agent configuration...")

    with tempfile.TemporaryDirectory() as temp_dir:
        base_dir = Path(temp_dir)
        config_manager = AgentConfigManager(base_dir)

        # Load non-existent config (should return default)
        config = await config_manager.load_agent_config("new_agent")
        assert config.name == "new_agent"
        assert config.session_config.session_mode.value == "time_based"

        # Save config
        config.purpose = "Test agent for unit testing"
        config.can_access_other_agents = ["agent2"]

        await config_manager.save_agent_config(config)

        # Load again
        config2 = await config_manager.load_agent_config("new_agent")
        assert config2.purpose == "Test agent for unit testing"
        assert "agent2" in config2.can_access_other_agents

        # Test purpose file
        await config_manager.save_agent_purpose("new_agent", "Updated purpose")
        purpose = await config_manager.load_agent_purpose("new_agent")
        assert purpose == "Updated purpose"

        print("✓ Agent configuration works correctly")


async def test_cross_agent_access():
    """Test cross-agent access control."""
    print("Testing cross-agent access control...")

    with tempfile.TemporaryDirectory() as temp_dir:
        base_dir = Path(temp_dir)
        config_manager = AgentConfigManager(base_dir)

        # Create two agents
        agent1_config = await config_manager.load_agent_config("agent1")
        agent1_config.can_access_other_agents = ["agent2"]
        await config_manager.save_agent_config(agent1_config)

        agent2_config = await config_manager.load_agent_config("agent2")
        agent2_config.can_access_other_agents = []  # No access
        await config_manager.save_agent_config(agent2_config)

        # Test access
        assert await config_manager.check_agent_access("agent1", "agent2")
        assert not await config_manager.check_agent_access("agent2", "agent1")
        assert await config_manager.check_agent_access("agent1", "agent1")

        # Test accessible agents
        accessible = await config_manager.get_accessible_agents("agent1")
        assert "agent1" in accessible
        assert "agent2" in accessible

        accessible = await config_manager.get_accessible_agents("agent2")
        assert "agent2" in accessible
        assert "agent1" not in accessible

        print("✓ Cross-agent access control works correctly")


async def test_memory_tools():
    """Test memory management tools."""
    print("Testing memory management tools...")

    with tempfile.TemporaryDirectory() as temp_dir:
        base_dir = Path(temp_dir)
        session_manager = SessionManager(base_dir)
        config_manager = AgentConfigManager(base_dir)
        memory_manager = MemoryManager(session_manager, config_manager)
        memory_tools = MemoryTools(memory_manager)

        # Create session
        session = await session_manager.get_or_create_session(
            "test_agent", "telegram", "chat_123"
        )

        # Test updating memories
        result1 = await memory_tools.update_agent_memory(
            session, "User is a Python developer", 4
        )
        assert "Added to agent memory" in result1

        result2 = await memory_tools.update_channel_memory(
            session, "Chat is about async programming"
        )
        assert "Added to channel memory" in result2

        # Test memory status
        status = await memory_tools.get_memory_status(session)
        assert "Session ID:" in status
        assert "Messages:" in status

        # Test query archived (should be empty initially)
        result = await memory_tools.query_archived_sessions(session, "python", 3)
        assert "No relevant archived sessions found" in result

        print("✓ Memory management tools work correctly")


async def main():
    """Run all tests."""
    print("Running session and memory management tests...\n")

    tests = [
        test_session_creation,
        test_thread_sessions,
        test_session_archiving,
        test_memory_context,
        test_agent_config,
        test_cross_agent_access,
        test_memory_tools,
    ]

    for test in tests:
        try:
            await test()
        except Exception as e:
            print(f"✗ Test failed: {e}")
            import traceback

            traceback.print_exc()
            return 1
        print()

    print("All tests passed! ✓")
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
