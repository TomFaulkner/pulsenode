#!/usr/bin/env python3

import asyncio
import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pulsenode.agent.sessions import SessionManager
from pulsenode.agent.memory import MemoryManager
from pulsenode.agent.agent_config import AgentConfigManager


async def demo_session_memory():
    """Demonstrate the new session and memory system."""
    print("🚀 PulseNode Session & Memory System Demo")
    print("=" * 50)

    # Use a temporary directory for demo
    demo_dir = Path.home() / ".pulsenode_demo"
    demo_dir.mkdir(exist_ok=True)

    try:
        # Initialize managers
        session_manager = SessionManager(demo_dir)
        memory_manager = MemoryManager(session_manager)
        config_manager = AgentConfigManager(demo_dir)

        print(f"📁 Using demo directory: {demo_dir}")
        print()

        # 1. Create an agent and configure it
        print("1️⃣ Creating and configuring agent...")
        config = await config_manager.load_agent_config("demo_agent")
        config.purpose = "Demo agent for showcasing session and memory management"
        await config_manager.save_agent_config(config)
        await config_manager.save_agent_purpose(
            "demo_agent",
            "I'm a demo agent that helps users with Python programming and async patterns.",
        )

        print(f"✅ Agent 'demo_agent' configured")
        print(f"   Purpose: {config.purpose}")
        print()

        # 2. Create a session for a Telegram chat
        print("2️⃣ Creating session for Telegram chat...")
        session = await session_manager.get_or_create_session(
            "demo_agent", "telegram", "chat_123456"
        )

        print(f"✅ Session created: {session.session_id}")
        print(f"   Channel: {session.channel_type}:{session.channel_identifier}")
        print()

        # 3. Add some conversation
        print("3️⃣ Adding conversation to session...")
        messages = [
            ("user", "Hi! I'm learning async programming in Python. Can you help?"),
            (
                "agent",
                "Absolutely! Async programming is powerful. What specific aspect are you struggling with?",
            ),
            ("user", "I'm confused about when to use asyncio vs threading."),
            (
                "agent",
                "Great question! Use asyncio for I/O-bound tasks like HTTP requests, database queries, and file operations. Use threading for CPU-bound tasks where you need true parallelism.",
            ),
            (
                "user",
                "Thanks! That makes sense. I'm building a Discord bot - should I use asyncio?",
            ),
            (
                "agent",
                "Definitely! Discord bots do a lot of I/O (API calls, database access). Asyncio will be much more efficient than threading for your use case.",
            ),
        ]

        for role, content in messages:
            session.add_message(role, content)

        await session_manager.save_session(session)
        print(f"✅ Added {len(messages)} messages to session")
        print()

        # 4. Update agent and channel memory
        print("4️⃣ Updating long-term memories...")
        await session_manager.update_agent_memory(
            "demo_agent", "User is learning Python async programming", importance=4
        )
        await session_manager.update_agent_memory(
            "demo_agent", "User is building a Discord bot", importance=3
        )

        await session_manager.update_channel_memory(
            "demo_agent",
            "telegram",
            "chat_123456",
            "This chat is focused on async programming and Discord bot development",
        )

        print("✅ Updated agent and channel memories")
        print()

        # 5. Generate context for LLM
        print("5️⃣ Generating context for LLM...")
        context = await memory_manager.get_context_for_llm(
            session, "How do I handle rate limits in Discord bots?"
        )

        print("📋 Context includes:")
        if "Agent Knowledge" in context:
            print("   ✅ Agent Knowledge (cross-channel facts)")
        if "Channel Context" in context:
            print("   ✅ Channel Context (channel-specific facts)")
        if "Recent History Summary" in context:
            print("   ✅ Recent History Summary")
        if "Recent Messages" in context:
            print("   ✅ Recent Messages")

        print()
        print("📝 Sample context (first 500 chars):")
        print(context[:500] + "..." if len(context) > 500 else context)
        print()

        # 6. Archive session and create new one
        print("6️⃣ Demonstrating session archiving...")
        archived_session = await memory_manager.archive_and_create_new_session(
            session, "Python async programming help", ["python", "asyncio", "discord"]
        )

        print(f"✅ Archived session to: {session.archived_sessions_dir}")
        print(f"✅ Created new session: {archived_session.session_id}")
        print()

        # 7. Query archived sessions
        print("7️⃣ Querying archived sessions...")
        results = await session_manager.query_archived_sessions(
            "demo_agent", "telegram", "chat_123456", "python", limit=3
        )

        if results:
            print(f"📚 Found {len(results)} relevant archived session(s):")
            for i, result in enumerate(results, 1):
                print(f"   {i}. {result.session_id}")
                print(f"      Summary: {result.summary}")
                print(f"      Topics: {', '.join(result.topics)}")
        else:
            print("📚 No archived sessions found")
        print()

        # 8. Show directory structure
        print("8️⃣ Generated directory structure:")

        def print_tree(path, prefix=""):
            if path.is_dir():
                print(f"{prefix}📁 {path.name}/")
                for item in sorted(path.iterdir()):
                    print_tree(item, prefix + "   ")
            else:
                print(f"{prefix}📄 {path.name}")

        agent_dir = demo_dir / "agents" / "demo_agent"
        if agent_dir.exists():
            print_tree(agent_dir)

        print()
        print("🎉 Demo completed successfully!")
        print(f"💾 Demo data saved in: {demo_dir}")
        print("🧹 Clean up with: rm -rf ~/.pulsenode_demo")

    except Exception as e:
        print(f"❌ Demo failed: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(demo_session_memory())
