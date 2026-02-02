import json
import logging
import asyncio
from dataclasses import dataclass
from datetime import datetime, UTC
from typing import Any, AsyncGenerator

from pulsenode.config import main_settings
from pulsenode.agent.llm_mcp import LlmMcp

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

# Config: Replace with your MCP server details
MCP_TRIAGE_LLM_URL = "http://your-mcp-server/triage-llm/infer"  # Cheap LLM endpoint
MCP_CAPABLE_LLM_URL = "http://your-mcp-server/capable-llm/infer"  # Better LLM endpoint
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

    async def receive_messages(self) -> AsyncGenerator[list[str]]:
        while True:                               # infinite loop
            try:
                # new_messages = await self.poll_or_wait_for_next()  # e.g. await websocket.recv(), imap idle, webhook wait, etc.
                new_messages: list[str] = []
                if self.fake_messages:
                    new_messages = [f"ntest message from {self.name} at {datetime.now(UTC)}", "empty message"]
                for msg in new_messages:
                    await asyncio.sleep(3)  # for fake purposes, don't include this in real code
                    yield msg                     # produce one message at a time
                else:
                    await asyncio.sleep(3)  # for fake purposes, don't include this in real code
                    yield []
            except asyncio.CancelledError:
                raise                             # allow clean shutdown
            except Exception as e:
                logger.warning("Recoverable error, retrying...")
                await asyncio.sleep(5)            # backoff & continue

class Agent:
    def __init__(
        self,
        triage_llm: LlmMcp,
        capable_llm: LlmMcp,
        context: Context,
        channels: list[ChannelMcp],
        settings: Any = main_settings,
    ):
        self.memory = []  # Simple list for conversation history
        self.channels = channels
        self.incoming_queue = asyncio.Queue()
        self._running = False
        self.settings = settings
        self.triage_llm = triage_llm
        self.capable_llm = capable_llm

    async def heartbeat(self):
        await self.start_channel_listeners()  # only once
        self._running = True

        while self._running:
            logger.info("Heartbeat: Checking for new inputs...")
            # Non-blocking drain of whatever arrived since last heartbeat
            pending = []
            while not self.incoming_queue.empty():
                pending.append(await self.incoming_queue.get())
                if len(pending) > 10:
                    break

            for _, msg in pending:
                is_action_needed = await self.triage_message(msg)  # or batch them
                if is_action_needed["needed"]:
                    response = await self.execute_task(msg, is_action_needed["reason"])
                    logger.info(f"Response: {response}")
                    self.send_response(response)
                else:
                    logger.info("No action needed for message.")

            # Optional: also run scheduled jobs here

            await asyncio.sleep(self.settings.heartbeat_interval_seconds)

    async def start_channel_listeners(self):
        async def listener(channel):
            try:
                async for msg in channel.receive_messages():  # async generator forever
                    if msg:
                        logger.debug("Queuing: %s", msg)
                        await self.incoming_queue.put((channel.name, msg))
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
            task.cancel()

        # Wait for them to actually stop (they should see CancelledError)
        await asyncio.gather(*self._listener_tasks, return_exceptions=True)

        # Optional: drain queue one last time, close connections, etc.

    async def triage_message(self, msg: str) -> dict[str, Any]:
        # Prompt for cheap LLM: Keep short for low cost
        prompt = f"Message: {msg}\nIs action needed? Respond JSON: {{'needed': bool, 'reason': str}}"
        response = await self.triage_llm.generate_triage_response(prompt)
        return {"needed": response.needed, "reason": response.reason}

    async def execute_task(self, msg: str, reason: str) -> str:
        # Use capable LLM via MCP
        full_prompt = f"Task reason: {reason}\nMessage: {msg}\nHistory: {self.memory}\nRespond appropriately."
        output = await self.capable_llm.generate_response(full_prompt)
        if output:
            self.memory.append({"user": msg, "agent": output})
            # Optionally call tools via MCP if needed (e.g., if output instructs)
            if "tool:" in output:
                tool_result = self.call_tool(output.split("tool:")[1])
                return f"{output} (Tool result: {tool_result})"
            return output
        return "Error executing task."

    def call_tool(self, tool: str) -> str:
        # Example: MCP tool call
        if tool == 'hello_world':
            return 'hello world!'
        return ''

        # response = requests.post(
        #     MCP_TOOL_URL,
        #     headers={"Authorization": f"Bearer {MCP_AUTH_TOKEN}"},
        #     json={"tool": tool},
        # )
        # return response.json().get("result", "Tool failed")

    def send_response(self, response: str):
        # Mock: Print. Real: Push to channel via MCP
        logger.info(f"Sending response: {response}")


async def main():
    triage_llm = LlmMcp(
        mcp_url=MCP_TRIAGE_LLM_URL, auth_token=MCP_AUTH_TOKEN, max_tokens=50
    )
    capable_llm = LlmMcp(
        mcp_url=MCP_CAPABLE_LLM_URL, auth_token=MCP_AUTH_TOKEN, max_tokens=500
    )
    context = Context(now=datetime.now(UTC))
    channels = [
        ChannelMcp(
            mcp_url="http://your-mcp-server/channels/telegram",
            name="TelegramChannel",
            type="telegram",
            identifier="chat_id_123",
            fake_messages=True,
        ),
        ChannelMcp(
            mcp_url="http://your-mcp-server/channels/email",
            name="EmailChannel",
            type="email",
            identifier="email",
        ),
    ]
    agent = Agent(
        triage_llm=triage_llm,
        capable_llm=capable_llm,
        context=context,
        channels=channels,
    )
    await agent.heartbeat()


if __name__ == "__main__":
    asyncio.run(main())
