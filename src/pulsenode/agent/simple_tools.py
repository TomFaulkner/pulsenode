"""Simple Tool Executor for demo purposes."""

import json
import asyncio
from pathlib import Path
from typing import Any, Dict
from dataclasses import dataclass, field

from structlog import get_logger

logger = get_logger(__name__)


@dataclass
class ToolCall:
    """Represents a tool call request."""

    tool_type: str  # "shell", "file", "http"
    action: str  # "exec", "read", "write", "get", etc.
    args: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResult:
    """Represents the result of a tool execution."""

    success: bool
    output: str
    error: str | None = None
    execution_time: float = 0.0


class SimpleToolExecutor:
    """Simple tool executor for demo."""

    def __init__(self, allowed_commands: list, allowed_directories: list):
        self.allowed_commands = set(allowed_commands)
        self.allowed_directories = [
            Path(d).expanduser().resolve() for d in allowed_directories
        ]
        self.home_dir = Path.home().resolve()

    async def execute_tool_call(self, tool_call: ToolCall) -> ToolResult:
        """Execute a tool call with security checks."""
        asyncio.get_event_loop().time()

        try:
            if tool_call.tool_type == "shell":
                return await self._execute_shell(tool_call)
            elif tool_call.tool_type == "file":
                return await self._execute_file(tool_call)
            else:
                return ToolResult(
                    success=False, error=f"Unknown tool type: {tool_call.tool_type}"
                )
        except Exception as e:
            logger.error("tool_execution_error", error=str(e))
            return ToolResult(success=False, error=f"Tool execution failed: {str(e)}")

    async def _execute_shell(self, tool_call: ToolCall) -> ToolResult:
        """Execute shell command."""
        start_time = asyncio.get_event_loop().time()
        command = tool_call.args.get("command", "")
        base_command = command.strip().split()[0]

        if base_command not in self.allowed_commands:
            return ToolResult(
                success=False, error=f"Command '{base_command}' is not allowed"
            )

        try:
            process = await asyncio.create_subprocess_shell(
                command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                return ToolResult(
                    success=True,
                    output=stdout.decode("utf-8", errors="replace"),
                    execution_time=asyncio.get_event_loop().time() - start_time,
                )
            else:
                return ToolResult(
                    success=False,
                    output="",
                    error=stderr.decode("utf-8", errors="replace"),
                )

        except Exception as e:
            return ToolResult(success=False, error=f"Shell execution failed: {str(e)}")

    async def _execute_file(self, tool_call: ToolCall) -> ToolResult:
        """Execute file operation."""
        start_time = asyncio.get_event_loop().time()
        action = tool_call.args.get("action", "")
        path = tool_call.args.get("path", "")
        content = tool_call.args.get("content", "")
        resolved_path = Path(path).expanduser().resolve()

        # Check path is allowed
        if not self._is_path_allowed(path):
            return ToolResult(
                success=False,
                output="",
                error=f"Path '{resolved_path}' is outside allowed directories",
            )

        try:
            if action == "write":
                resolved_path.parent.mkdir(parents=True, exist_ok=True)
                with open(resolved_path, "w", encoding="utf-8") as f:
                    f.write(content)
                return ToolResult(
                    success=True,
                    output=f"File written: {path}",
                    execution_time=asyncio.get_event_loop().time() - start_time,
                )

            elif action == "read":
                if not resolved_path.exists():
                    return ToolResult(success=False, error=f"File not found: {path}")

                with open(resolved_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                return ToolResult(
                    success=True,
                    output=content,
                    execution_time=asyncio.get_event_loop().time() - start_time,
                )

            elif action == "list":
                if not resolved_path.exists():
                    return ToolResult(success=False, error=f"Path not found: {path}")

                if resolved_path.is_dir():
                    items = []
                    for item in sorted(resolved_path.iterdir()):
                        if item.is_dir():
                            items.append(f"📁 {item.name}/")
                        else:
                            items.append(f"📄 {item.name}")
                    output = "\n".join(items) if items else "Directory is empty"
                else:
                    output = f"Path is a file: {resolved_path.name}"

                return ToolResult(
                    success=True,
                    output=output,
                    execution_time=asyncio.get_event_loop().time() - start_time,
                )

            else:
                return ToolResult(success=False, error=f"Unknown file action: {action}")

        except Exception as e:
            return ToolResult(success=False, error=f"File operation failed: {str(e)}")

    def _is_path_allowed(self, path: str) -> bool:
        """Check if a path is within allowed directories."""
        resolved_path = Path(path).expanduser().resolve()

        # Check allowed directories
        for allowed_dir in self.allowed_directories:
            try:
                if resolved_path.is_relative_to(allowed_dir):
                    return True
            except ValueError:
                continue

        return False


class SimpleToolRegistry:
    """Simple tool registry."""

    def __init__(
        self, tool_executor: SimpleToolExecutor, system_capabilities: Dict = None
    ):
        self.tool_executor = tool_executor
        self.system_capabilities = system_capabilities or {}

    def parse_tool_call(self, text: str) -> ToolCall | None:
        """Parse tool call from LLM text."""
        import re

        # Pattern to match JSON tool calls
        pattern = r'\{\s*"tool":\s*"(\w+)"\s*,\s*"action":\s*"(\w+)"\s*,\s*(.*)\}'
        matches = re.findall(pattern, text, re.DOTALL)

        if not matches:
            return None

        tool_type, action, args_str = matches[0]

        try:
            # Parse arguments
            args_str = args_str.strip()
            if args_str.endswith("}"):
                args_str = args_str[:-1]  # Remove trailing brace

            args = json.loads("{" + args_str + "}")

            return ToolCall(tool_type=tool_type, action=action, args=args)
        except json.JSONDecodeError as e:
            logger.warning("tool_parse_error", text=text, error=str(e))
            return None

    async def execute_tool_from_text(self, text: str) -> ToolResult:
        """Parse and execute tool call from text."""
        tool_call = self.parse_tool_call(text)
        if not tool_call:
            return ToolResult(success=False, error="No valid tool call found in text")

        return await self.tool_executor.execute_tool_call(tool_call)

    def get_available_tools(self) -> str:
        """Get description of available tools."""
        return f"""
## Available Tools

You can use the following tools by outputting JSON:

### Shell Tools
{{"tool": "shell", "action": "exec", "command": "<command>"}}

### File Tools
{{"tool": "file", "action": "read|write|list", "path": "<path>", "content": "<optional_content>"}}

### System Capabilities
The following utilities are available: {", ".join(self.system_capabilities.get("available_utilities", []))}

### Security Notes
- Only allowed directories and commands are accessible
- Write operations create parent directories as needed
- Large files are handled appropriately

When you need to use a tool, output JSON and wait for the result before continuing.
"""
