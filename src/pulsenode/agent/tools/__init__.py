"""Tool System for PulseNode Agent.

Provides secure tool execution with approval workflow.
"""

from __future__ import annotations
from typing import final

import asyncio
import json
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from structlog import get_logger

from pulsenode.agent.agent_config import HttpConfig
from pulsenode.agent.tools.http import HttpTool

logger = get_logger(__name__)


@dataclass
class ToolCall:
    """Represents a tool call request."""

    tool_type: str  # "shell", "file", "http"
    action: str  # "exec", "read", "write", "get", etc.
    args: dict[str, Any] = field(default_factory=dict)
    requires_approval: bool = False
    approval_id: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class ToolResult:
    """Represents the result of a tool execution."""

    success: bool
    output: str = ""
    error: str | None = None
    execution_time: float = 0.0
    approval_granted: bool | None = None  # None if no approval needed


@dataclass
class ApprovalRequest:
    """Represents a pending approval request."""

    approval_id: str
    tool_call: ToolCall
    reason: str
    risk_level: str  # "low", "medium", "high"
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@final
class SecurityChecker:
    """Handles security validation for tool calls."""

    # Files that require approval for any operation
    SENSITIVE_FILE_PATTERNS: list[str] = [
        ".env",
        ".env.*",
        "*secret*",
        "*key*",
        "*password*",
        "*token*",
        "*.pem",
        "*.key",
        "*.p12",
        "id_rsa",
        "id_ed25519",
    ]

    # Binary file extensions that should be blocked for reading with cat
    BINARY_EXTENSIONS: set[str] = {
        ".pdf",
        ".zip",
        ".tar",
        ".gz",
        ".bz2",
        ".xz",
        ".7z",
        ".rar",
        ".exe",
        ".dll",
        ".so",
        ".dylib",
        ".a",
        ".o",
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".bmp",
        ".tiff",
        ".webp",
        ".mp3",
        ".wav",
        ".ogg",
        ".flac",
        ".m4a",
        ".mp4",
        ".avi",
        ".mkv",
        ".mov",
        ".wmv",
        ".flv",
        ".sqlite",
        ".db",
        ".mdb",
    }

    # Commands that are always considered safe
    SAFE_COMMANDS: set[str] = {
        "ls",
        "cat",
        "grep",
        "find",
        "which",
        "file",
        "stat",
        "head",
        "tail",
        "wc",
        "sort",
        "uniq",
        "cut",
        "awk",
        "sed",
        "tr",
        "df",
        "du",
        "ps",
        "top",
        "free",
        "whoami",
        "pwd",
        "date",
        "uptime",
        "tree",
        "locate",
        "whereis",
    }

    # Commands that are always considered dangerous
    DANGEROUS_COMMANDS: set[str] = {
        "rm",
        "rmdir",
        "dd",
        "mkfs",
        "fdisk",
        "format",
        "shutdown",
        "reboot",
        "halt",
        "poweroff",
        "passwd",
        "useradd",
        "usermod",
        "userdel",
        "chmod",
        "chown",
        "sudo",
        "su",
        "doas",
    }

    def __init__(
        self,
        allowed_commands: list[str],
        allowed_directories: list[str],
        access_home_directory: bool = False,
    ):
        self.allowed_commands = set(allowed_commands)
        self.allowed_directories = [
            Path(d).expanduser().resolve() for d in allowed_directories
        ]
        self.access_home_directory = access_home_directory
        self.home_dir = Path.home().resolve()

    def is_file_sensitive(self, file_path: str) -> bool:
        """Check if a file is considered sensitive."""
        import fnmatch

        file_name = Path(file_path).name
        for pattern in self.SENSITIVE_FILE_PATTERNS:
            if fnmatch.fnmatch(file_name.lower(), pattern.lower()):
                return True
        return False

    def is_file_binary(self, file_path: str) -> bool:
        """Check if a file extension indicates binary content."""
        file_ext = Path(file_path).suffix.lower()
        return file_ext in self.BINARY_EXTENSIONS

    def is_path_allowed(self, path: str) -> bool:
        """Check if a path is within allowed directories."""
        resolved_path = Path(path).expanduser().resolve()

        # Check home directory access
        if not self.access_home_directory:
            try:
                if resolved_path.is_relative_to(self.home_dir):
                    return False
            except ValueError:
                # Path is not relative, continue checking other directories
                pass

        # Check allowed directories
        for allowed_dir in self.allowed_directories:
            try:
                if resolved_path.is_relative_to(allowed_dir):
                    return True
            except ValueError:
                continue

        return False

    def check_shell_command(self, command: str) -> tuple[bool, str, str]:
        """Check if a shell command is allowed and safe."""
        # Extract the base command (first word)
        base_command = command.strip().split()[0]

        # Check if command is allowed
        if base_command not in self.allowed_commands:
            return False, "dangerous", f"Command '{base_command}' is not in allowlist"

        # Check if command is dangerous
        if base_command in self.DANGEROUS_COMMANDS:
            return False, "high", f"Command '{base_command}' is dangerous"

        # Check if command is safe (low risk)
        if base_command in self.SAFE_COMMANDS:
            return True, "low", f"Command '{base_command}' is safe"

        # Otherwise, medium risk
        return True, "medium", f"Command '{base_command}' requires confirmation"

    def check_file_operation(
        self, action: str, file_path: str
    ) -> tuple[bool, str, str]:
        """Check file operation permissions."""
        resolved_path = Path(file_path).expanduser().resolve()

        # Check path is allowed
        if not self.is_path_allowed(file_path):
            return (
                False,
                "high",
                f"Path '{resolved_path}' is outside allowed directories",
            )

        # Check sensitive files
        if self.is_file_sensitive(file_path):
            return (
                False,
                "high",
                f"File '{file_path}' is sensitive and requires approval",
            )

        # Check binary files for read operations
        if action in ["read", "cat"] and self.is_file_binary(file_path):
            return (
                False,
                "medium",
                f"File '{file_path}' appears to be binary - use appropriate tool",
            )

        # Check destructive operations
        if action in ["delete", "remove", "rm"]:
            return True, "medium", "File deletion requires confirmation"

        # Default: allowed with low risk
        return True, "low", f"File {action} is allowed"

    def get_risk_assessment(self, tool_call: ToolCall) -> tuple[bool, str, str]:
        """Assess the risk level of a tool call."""
        if tool_call.tool_type == "shell":
            command = tool_call.args.get("command", "")
            return self.check_shell_command(command)

        elif tool_call.tool_type == "file":
            action = tool_call.args.get("action", "")
            path = tool_call.args.get("path", "")
            return self.check_file_operation(action, path)

        elif tool_call.tool_type == "http":
            return True, "low", "HTTP requests are allowed"

        elif tool_call.tool_type == "container":
            # Container execution is medium-high risk
            return True, "medium-high", "Container execution requires confirmation"

        return (
            True,
            "medium",
            f"Unknown tool type '{tool_call.tool_type}' requires confirmation",
        )


class ApprovalManager:
    """Manages pending approval requests."""

    def __init__(self, timeout_seconds: int = 300):
        self.timeout_seconds = timeout_seconds
        self.pending_requests: dict[str, ApprovalRequest] = {}
        self.approvals: dict[str, bool] = {}
        self.approval_callbacks: dict[str, Callable[[bool], None]] = {}
        self._approval_counter = 0

    def generate_approval_id(self) -> str:
        """Generate a unique approval ID."""
        self._approval_counter += 1
        return f"approval_{int(time.time())}_{self._approval_counter}"

    async def request_approval(
        self, tool_call: ToolCall, reason: str, callback: Callable[[bool], None]
    ) -> str:
        """Request approval for a tool call."""
        approval_id = self.generate_approval_id()

        # Create approval request
        request = ApprovalRequest(
            approval_id=approval_id,
            tool_call=tool_call,
            reason=reason,
            risk_level=reason,  # Risk level passed as reason
        )

        self.pending_requests[approval_id] = request
        self.approval_callbacks[approval_id] = callback

        logger.info(
            "approval_requested",
            approval_id=approval_id,
            tool=tool_call.tool_type,
            action=tool_call.action,
            risk_level=reason,
        )

        # In a real implementation, this would send a message via the messaging channel
        # For now, we'll print and wait for approval
        print(f"\n🔐 Approval Request ({approval_id})")
        print(f"Tool: {tool_call.tool_type}.{tool_call.action}")
        print(f"Reason: {reason}")
        print(f"Risk Level: {reason}")
        print(f"\nPlease respond: approve {approval_id} OR deny {approval_id}")
        print(f"Timeout in {self.timeout_seconds} seconds")

        return approval_id

    async def respond_to_approval(self, approval_id: str, approved: bool) -> bool:
        """Respond to an approval request."""
        if approval_id not in self.pending_requests:
            logger.warning("approval_not_found", approval_id=approval_id)
            return False

        request = self.pending_requests[approval_id]
        self.approvals[approval_id] = approved

        logger.info(
            "approval_response",
            approval_id=approval_id,
            approved=approved,
            tool=request.tool_call.tool_type,
            action=request.tool_call.action,
        )

        # Call the callback
        if approval_id in self.approval_callbacks:
            callback = self.approval_callbacks[approval_id]
            callback(approved)

        # Clean up
        del self.pending_requests[approval_id]
        del self.approval_callbacks[approval_id]

        return True

    def check_timeout(self, approval_id: str) -> bool:
        """Check if an approval request has timed out."""
        if approval_id not in self.pending_requests:
            return False

        request = self.pending_requests[approval_id]
        elapsed = (datetime.now(UTC) - request.timestamp).total_seconds()

        if elapsed > self.timeout_seconds:
            logger.warning("approval_timeout", approval_id=approval_id)
            self.approvals[approval_id] = False

            # Call callback with rejection
            if approval_id in self.approval_callbacks:
                callback = self.approval_callbacks[approval_id]
                callback(False)

            # Clean up
            del self.pending_requests[approval_id]
            del self.approval_callbacks[approval_id]
            del self.approvals[approval_id]

            return True

        return False

    def get_pending_requests(self) -> list[ApprovalRequest]:
        """Get all pending approval requests."""
        return list(self.pending_requests.values())


class ToolExecutor:
    """Executes tools with security checks and approvals."""

    def __init__(
        self,
        security_checker: SecurityChecker,
        approval_manager: ApprovalManager,
        http_config: HttpConfig | None = None,
    ):
        self.security_checker = security_checker
        self.approval_manager = approval_manager
        self.http_tool = (
            HttpTool(http_config) if http_config and http_config.enabled else None
        )

    async def execute_tool_call(self, tool_call: ToolCall) -> ToolResult:
        """Execute a tool call with security checks."""
        start_time = time.time()

        try:
            # Security check
            allowed, risk_level, reason = self.security_checker.get_risk_assessment(
                tool_call
            )
            tool_call.requires_approval = not allowed or risk_level not in ["low"]

            if not allowed:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Operation not allowed: {reason}",
                    approval_granted=False,
                )

            # Check if approval needed
            if tool_call.requires_approval:
                # Request approval
                future = asyncio.Future()
                await self.approval_manager.request_approval(
                    tool_call, risk_level, future.set_result
                )

                # Wait for approval
                try:
                    approval_granted = await asyncio.wait_for(
                        future, timeout=self.approval_manager.timeout_seconds
                    )
                except asyncio.TimeoutError:
                    return ToolResult(
                        success=False,
                        error="Approval request timed out",
                        approval_granted=False,
                    )

                if not approval_granted:
                    return ToolResult(
                        success=False,
                        error="Operation denied by user approval",
                        approval_granted=False,
                    )

            # Execute the tool
            if tool_call.tool_type == "shell":
                result = await self._execute_shell_tool(tool_call)
            elif tool_call.tool_type == "file":
                result = await self._execute_file_tool(tool_call)
            elif tool_call.tool_type == "http":
                result = await self._execute_http_tool(tool_call)
            elif tool_call.tool_type == "container":
                result = await self._execute_container_tool(tool_call)
            else:
                result = ToolResult(
                    success=False,
                    error=f"Unknown tool type: {tool_call.tool_type}",
                    approval_granted=tool_call.requires_approval,
                )

            result.approval_granted = tool_call.requires_approval
            result.execution_time = time.time() - start_time

            return result

        except Exception as e:
            logger.error(
                "tool_execution_error",
                tool=tool_call.tool_type,
                action=tool_call.action,
                error=str(e),
            )
            return ToolResult(
                success=False,
                error=f"Tool execution failed: {str(e)}",
                execution_time=time.time() - start_time,
                approval_granted=tool_call.requires_approval,
            )

    async def _execute_shell_tool(self, tool_call: ToolCall) -> ToolResult:
        """Execute shell tool."""
        command = tool_call.args.get("command", "")
        working_dir = tool_call.args.get("working_dir", None)

        if working_dir:
            working_dir = str(Path(working_dir).expanduser().resolve())

        try:
            if working_dir:
                process = await asyncio.create_subprocess_shell(
                    command,
                    cwd=working_dir,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            else:
                process = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                return ToolResult(
                    success=True, output=stdout.decode("utf-8", errors="replace")
                )
            else:
                error_output = stderr.decode("utf-8", errors="replace")
            return ToolResult(
                success=False,
                output="",
                error=f"Command failed with exit code {process.returncode}: {error_output}",
            )

        except Exception as e:
            return ToolResult(success=False, error=f"Shell execution failed: {str(e)}")

    async def _execute_file_tool(self, tool_call: ToolCall) -> ToolResult:
        """Execute file tool."""
        action = tool_call.args.get("action", "")
        path = tool_call.args.get("path", "")
        content = tool_call.args.get("content", "")

        resolved_path = Path(path).expanduser().resolve()

        try:
            if action == "read":
                if not resolved_path.exists():
                    return ToolResult(
                        success=False,
                        error=f"File not found: {path}",
                        execution_time=0.0,
                    )

                # Check file size for large files
                file_size = resolved_path.stat().st_size
                max_size = 1024 * 100  # 100KB limit

                if file_size > max_size:
                    # Save to file and return path
                    output_file = Path("/tmp") / f"tool_output_{int(time.time())}.txt"
                    shutil.copy2(resolved_path, output_file)
                    return ToolResult(
                        success=True,
                        output=f"File too large ({file_size} bytes). Content saved to: {output_file}",
                        execution_time=0.0,
                    )

                with open(resolved_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                return ToolResult(success=True, output=content)

            elif action == "write":
                resolved_path.parent.mkdir(parents=True, exist_ok=True)
                with open(resolved_path, "w", encoding="utf-8") as f:
                    f.write(content)
                return ToolResult(success=True, output=f"File written: {path}")

            elif action == "append":
                resolved_path.parent.mkdir(parents=True, exist_ok=True)
                with open(resolved_path, "a", encoding="utf-8") as f:
                    f.write(content)
                return ToolResult(success=True, output=f"Content appended to: {path}")

            elif action == "delete":
                if not resolved_path.exists():
                    return ToolResult(success=False, error=f"File not found: {path}")

                if resolved_path.is_dir():
                    shutil.rmtree(resolved_path)
                    return ToolResult(success=True, output=f"Directory deleted: {path}")
                else:
                    resolved_path.unlink()
                    return ToolResult(success=True, output=f"File deleted: {path}")

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
                    return ToolResult(success=True, output=output)
                else:
                    return ToolResult(
                        success=True, output=f"Path is a file: {resolved_path.name}"
                    )

            elif action == "exists":
                exists = resolved_path.exists()
                file_type = "directory" if exists and resolved_path.is_dir() else "file"
                output = f"{'exists' if exists else 'does not exist'}"
                if exists:
                    output += f" (and is a {file_type})"
                return ToolResult(success=True, output=output)

            else:
                return ToolResult(success=False, error=f"Unknown file action: {action}")

        except Exception as e:
            return ToolResult(success=False, error=f"File operation failed: {str(e)}")

    async def _execute_http_tool(self, tool_call: ToolCall) -> ToolResult:
        """Execute HTTP tool."""
        if not self.http_tool:
            return ToolResult(success=False, error="HTTP tool is not enabled")

        method = tool_call.args.get("method", "GET").upper()
        url = tool_call.args.get("url", "")
        headers = tool_call.args.get("headers", {})
        body = tool_call.args.get("body", "")
        timeout = tool_call.args.get("timeout")

        if not url:
            return ToolResult(success=False, error="URL is required")

        try:
            result = await self.http_tool.request(
                method=method,
                url=url,
                headers=headers if headers else None,
                body=body if body else None,
                timeout=timeout,
            )

            if result["success"]:
                output = (
                    f"Status: {result['status_code']} {result.get('status_text', '')}\n"
                )
                output += f"Time: {result['response_time']:.2f}s\n\n"
                output += result["body"]
                return ToolResult(
                    success=True,
                    output=output,
                    execution_time=result["response_time"],
                )
            else:
                return ToolResult(
                    success=False,
                    error=result.get("error", "Request failed"),
                    execution_time=result.get("response_time", 0.0),
                )

        except Exception as e:
            return ToolResult(success=False, error=f"HTTP tool failed: {str(e)}")

    async def _execute_container_tool(self, tool_call: ToolCall) -> ToolResult:
        """Execute container tool (placeholder implementation)."""
        # TODO: Implement container execution
        return ToolResult(success=False, error="Container tool not yet implemented")


@final
class ToolRegistry:
    """Registry for available tools."""

    def __init__(
        self, tool_executor: ToolExecutor, system_capabilities: dict | None = None
    ):
        self.tool_executor = tool_executor
        self.system_capabilities = system_capabilities or {}

    def parse_tool_call(self, text: str) -> ToolCall | None:
        """Parse tool call from LLM text."""
        import re

        # Pattern to match JSON tool calls - accepts both "action" and "method" keys
        pattern = (
            r'\{\s*"tool":\s*"(\w+)"\s*,\s*"(method|action)":\s*"(\w+)"\s*,\s*(.*)\}'
        )
        matches = re.findall(pattern, text, re.DOTALL)

        if not matches:
            return None

        tool_type, key_name, action, args_str = matches[0]

        try:
            args_str = args_str.strip()
            if args_str.endswith("}"):
                args_str = args_str[:-1]

            args = json.loads("{" + args_str + "}")

            # Normalize "method" to "action" in args if needed
            if "method" in args:
                args["action"] = args.pop("method")

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
        return (
            """
## Available Tools

You can use the following tools by outputting JSON:

### Shell Tools
{"tool": "shell", "action": "exec", "command": "<command>", "working_dir": "<optional_path>"}

### File Tools
{"tool": "file", "action": "read|write|append|delete|list|exists", "path": "<path>", "content": "<optional_content>"}

### HTTP Tools
{"tool": "http", "method": "GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS", "url": "<url>", "headers": {}, "body": "<optional_body>", "timeout": <optional_seconds>}

### Container Tools (Coming Soon)
{"tool": "container", "image": "debian:latest", "command": "<command>"}

### System Capabilities
The following utilities are available: """
            + ", ".join(self.system_capabilities.get("available_utilities", []))
            + """

### Security Notes
- Sensitive files (.env, *secret*, *key*, *password*, *token*) require approval
- Destructive operations (rm, mv overwriting) require approval
- File operations restricted to allowed directories
- Large files (>100KB) will be saved to temporary location

When you need to use a tool, output JSON and wait for the result before continuing.
"""
        )
