import logging
import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, UTC
from typing import TypedDict
from collections.abc import AsyncGenerator
from pathlib import Path

import structlog

from pulsenode.config.settings import settings, create_default_settings, Settings
from pulsenode.agent.llm_mcp import LlmMcp
from pulsenode.agent.sessions import SessionManager, Session
from pulsenode.agent.memory import MemoryManager, MemoryTools
from pulsenode.agent.agent_config import AgentConfigManager
from pulsenode.agent.tools import (
    ToolExecutor,
    SecurityChecker,
    ApprovalManager,
    ToolRegistry,
)
from pulsenode.agent.channels import FileChannelMcp

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)


logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = structlog.getLogger(__name__)

# Config: Replace with your MCP server details
MCP_TRIAGE_LLM_URL = "http://localhost:8000/mcp"
MCP_CAPABLE_LLM_URL = MCP_TRIAGE_LLM_URL
MCP_AUTH_TOKEN = "your-mcp-token"  # Server-side auth, not API keys

# Mock channel: In real, this would poll Telegram/email via MCP
MESSAGE_QUEUE_FILE = "message_queue.json"  # Simulate incoming messages


@dataclass
class Context:
    now: datetime

    async def refresh(self):
        self.now = datetime.now(UTC)


@dataclass
class ChannelMcp:
    mcp_url: str

    name: str
    type: str  # e.g., "telegram", "email"
    identifier: str  # e.g., chat_id, email address
    fake_messages: bool = False
    thread_id: str | None = None  # For email threads or other threaded channels

    async def receive_messages(self) -> AsyncGenerator[str]:
        while True:  # infinite loop
            try:
                # new_messages = await self.poll_or_wait_for_next()  # e.g. await websocket.recv(), imap idle, webhook wait, etc.
                new_messages: list[str] = []
                if self.fake_messages:
                    new_messages = [
                        f"ntest message from {self.name} at {datetime.now(UTC)}",
                        "empty message",
                    ]
                for msg in new_messages:
                    await asyncio.sleep(
                        3
                    )  # for fake purposes, don't include this in real code
                    yield msg  # produce one message at a time
                else:
                    await asyncio.sleep(
                        3
                    )  # for fake purposes, don't include this in real code
                    yield ""
            except asyncio.CancelledError:
                raise  # allow clean shutdown
            except Exception:
                logger.warning("Recoverable error, retrying...")
                await asyncio.sleep(5)  # backoff & continue


class TriageResponse(TypedDict):
    needed: bool
    reason: str


class Agent:
    def __init__(
        self,
        triage_llm: LlmMcp,
        capable_llm: LlmMcp,
        context: Context,
        channels: list[ChannelMcp],
        agent_name: str = "default_agent",
        pulsenode_dir: Path | None = None,
        settings: Settings = settings or create_default_settings(),
    ):
        self.agent_name: str = agent_name
        self.channels: list[ChannelMcp] = channels
        self.incoming_queue: asyncio.Queue[tuple[str, str, str]] = (
            asyncio.Queue()
        )  # (session_id, channel_name, msg)
        self._running: bool = False
        self.settings: Settings = settings or create_default_settings()
        self.triage_llm: LlmMcp = triage_llm
        self.capable_llm: LlmMcp = capable_llm
        self._listener_tasks: list[asyncio.Task[None]] = []

        # Initialize session and memory management
        base_dir = pulsenode_dir or Path.home() / ".pulsenode"
        self.session_manager = SessionManager(base_dir)
        self.memory_manager = MemoryManager(self.session_manager)
        self.memory_tools = MemoryTools(self.memory_manager)
        self.config_manager = AgentConfigManager(base_dir)

        # Load system capabilities for tools
        system_capabilities_file = base_dir / "system_capabilities.json"
        if system_capabilities_file.exists():
            with open(system_capabilities_file, "r") as f:
                self.system_capabilities = json.load(f)
        else:
            self.system_capabilities = {}

        # Initialize tool system (will be configured per agent)
        self.tool_executor: ToolExecutor | None = None
        self.tool_registry: ToolRegistry | None = None

        # Map to track which session is used for each message
        self._message_sessions: dict[str, str] = {}  # temp_id -> session_id

    async def heartbeat(self):
        # Initialize tool system before starting
        await self._initialize_tool_system()

        await self.start_channel_listeners()
        self._running = True

        while self._running:
            logger.info("Heartbeat: Checking for new inputs...")
            # Non-blocking drain of whatever arrived since last heartbeat
            pending: list[tuple[str, str, str]] = []
            while not self.incoming_queue.empty():
                pending.append(await self.incoming_queue.get())
                if len(pending) > 10:
                    break

            for session_id, channel_name, msg in pending:
                is_action_needed = await self.triage_message(msg)  # or batch them
                if is_action_needed["needed"]:
                    response = await self.execute_task(
                        session_id, msg, is_action_needed["reason"]
                    )
                    logger.info(f"Response: {response}")
                    self.send_response(response, channel_name)
                else:
                    logger.info("No action needed for message.")

            # Optional: also run scheduled jobs here

            # Check for session rollover
            await self._check_session_rollover()

            await asyncio.sleep(self.settings.heartbeat_interval_seconds)

    async def start_channel_listeners(self):
        async def listener(channel: ChannelMcp):
            try:
                async for msg in channel.receive_messages():
                    if msg:
                        logger.debug("Queuing: %s", msg)
                        # Create session ID for this channel
                        session_id = await self._get_session_id_for_channel(channel)
                        await self.incoming_queue.put((session_id, channel.name, msg))
            except Exception as exc:
                logger.error(f"Channel {channel.name} died: {exc}")
                # optionally restart or mark dead

        # Launch one background task per channel
        self._listener_tasks = [
            asyncio.create_task(listener(ch)) for ch in self.channels
        ]

    async def shutdown(self):
        self._running = False

        # Cancel all listener tasks
        for task in self._listener_tasks:
            _ = task.cancel()

        # Wait for them to actually stop (they should see CancelledError)
        _ = await asyncio.gather(*self._listener_tasks, return_exceptions=True)

        # Optional: drain queue one last time, close connections, etc.

    async def triage_message(self, msg: str) -> TriageResponse:
        # Prompt for cheap LLM: Keep short for low cost
        prompt = f"""Message: {msg}

Is action needed? Respond JSON: {{'needed': bool, 'reason': str}}

Guidelines:
- Questions asking for information (weather, facts, calculations) -> needed: true
- User providing a URL to fetch data from -> needed: true
- Greetings -> needed: false
- Simple acknowledgments -> needed: false"""
        response = await self.triage_llm.generate_triage_response(prompt)
        return {"needed": response.needed, "reason": response.reason}

    async def execute_task(self, session_id: str, msg: str, reason: str) -> str:
        # Get session
        session = self.session_manager.sessions.get(session_id)
        if not session:
            return "Error: Session not found"

        # Get context including all memory tiers
        context = await self.memory_manager.get_context_for_llm(session, msg)

        # Add tool information to context
        if self.tool_registry:
            context += self.tool_registry.get_available_tools()

        # Use capable LLM via MCP with full context
        full_prompt = f"""Context:
{context}

User Message: {msg}

Use the available tools to complete the task if needed. When you use a tool, output the tool call as JSON (e.g., {{"tool": "http", "method": "GET", "url": "..."}}). After getting tool results, provide your final response."""
        output = await self.capable_llm.generate_response(full_prompt)

        if output:
            # Add to session memory
            session.add_message("user", msg)
            session.add_message("agent", output)

            # Save session
            await self.session_manager.save_session(session)

            # Handle tool calls in output
            if self.tool_registry:
                output = await self._handle_tool_calls(session, output)

            return output
        return "Error executing task."

    def call_tool(self, tool: str) -> str:
        # Example: MCP tool call
        if tool == "hello_world":
            return "hello world!"
        return ""

        # response = requests.post(
        #     MCP_TOOL_URL,
        #     headers={"Authorization": f"Bearer {MCP_AUTH_TOKEN}"},
        #     json={"tool": tool},
        # )
        # return response.json().get("result", "Tool failed")

    def send_response(self, response: str, channel_name: str):
        # Mock: Print. Real: Push to channel via MCP
        logger.info(f"Sending response to {channel_name}: {response}")

    async def _get_session_id_for_channel(self, channel: ChannelMcp) -> str:
        """Get or create session ID for a channel message."""
        session = await self.session_manager.get_or_create_session(
            self.agent_name,
            channel.type,
            channel.identifier,
            channel.thread_id,  # Support thread-based sessions for email
        )
        return session.session_id

    async def _initialize_tool_system(self) -> None:
        """Initialize tool system for this agent."""
        # Load agent configuration
        agent_config = await self.config_manager.load_agent_config(self.agent_name)

        if not agent_config.tools.enabled:
            logger.info("tools_disabled", agent_name=self.agent_name)
            return

        # Setup file directories
        workspace_dir = (
            Path(self.settings.pulsenode_directory)
            / "agents"
            / self.agent_name
            / self.settings.default_workspace_dir
        )
        workspace_dir.mkdir(parents=True, exist_ok=True)

        # Setup allowed directories for file operations
        allowed_dirs = [str(workspace_dir)]
        if agent_config.tools.file.access_home_directory:
            allowed_dirs.append(str(Path.home()))
        allowed_dirs.extend(agent_config.tools.file.allowed_directories)

        # Initialize security checker
        security_checker = SecurityChecker(
            allowed_commands=agent_config.tools.shell.allowlist,
            allowed_directories=allowed_dirs,
            access_home_directory=agent_config.tools.file.access_home_directory,
        )

        # Initialize approval manager
        approval_manager = ApprovalManager(
            timeout_seconds=agent_config.tools.approval_timeout_seconds
        )

        # Initialize tool executor
        self.tool_executor = ToolExecutor(
            security_checker,
            approval_manager,
            agent_config.tools.http,
        )

        # Initialize tool registry
        self.tool_registry = ToolRegistry(self.tool_executor, self.system_capabilities)

        logger.info("tools_initialized", agent_name=self.agent_name)

    async def _handle_tool_calls(self, session: Session, output: str) -> str:
        """Handle tool calls in LLM output."""
        if not self.tool_registry:
            return output

        # Parse and execute all tool calls in the output
        results = []
        remaining_text = output

        # Simple parsing - look for JSON tool calls
        import re

        # Pattern to find JSON tool calls - more permissive for URLs and nested content
        pattern = r'\{"tool":\s*"[^"]+"(?:,\s*"[^"]+":\s*"[^"]+")*\}'

        tool_calls = re.findall(pattern, output)

        for tool_call_json in tool_calls:
            try:
                tool_result = await self.tool_registry.execute_tool_from_text(
                    tool_call_json
                )

                if tool_result.success:
                    result_text = f"Tool result: {tool_result.output}"
                else:
                    result_text = f"Tool error: {tool_result.error}"

                results.append(result_text)

                # Replace the tool call with the result
                remaining_text = remaining_text.replace(tool_call_json, result_text)

            except Exception as e:
                logger.error("tool_call_error", error=str(e))
                results.append(f"Tool call failed: {str(e)}")

        if results:
            return f"{output}\n\nTool Results:\n" + "\n".join(results)

        return output

    async def _check_session_rollover(self):
        """Check if any sessions need to be archived."""
        for session in list(self.session_manager.sessions.values()):
            should_archive, reason = await self.memory_manager.should_archive_session(
                session
            )

            if should_archive:
                logger.info(f"Rolling over session {session.session_id}: {reason}")
                await self.memory_manager.archive_and_create_new_session(session)
                # The session reference in session_manager will be updated


async def main():
    triage_llm = LlmMcp(
        mcp_url=MCP_TRIAGE_LLM_URL, auth_token=MCP_AUTH_TOKEN, max_tokens=50
    )
    capable_llm = LlmMcp(
        mcp_url=MCP_CAPABLE_LLM_URL, auth_token=MCP_AUTH_TOKEN, max_tokens=500
    )
    context = Context(now=datetime.now(UTC))
    channels = [
        FileChannelMcp(
            file_path=Path("debug_messages.txt"),
            name="DebugChannel",
            type="debug",
            identifier="test",
            sleep_seconds=1.0,
        ),
    ]
    agent = Agent(
        triage_llm=triage_llm,
        capable_llm=capable_llm,
        context=context,
        channels=channels,
        agent_name="demo_agent",
    )
    await agent.heartbeat()


if __name__ == "__main__":
    asyncio.run(main())
