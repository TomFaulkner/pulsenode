import json
import re
from typing import Any

from pulsenode.agent.tools.parsers.base import ToolCallParser


TOOL_DEFINITIONS = {
    "shell": {
        "description": "Execute shell commands on the system",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute",
                },
                "working_dir": {
                    "type": "string",
                    "description": "Optional working directory for the command",
                },
            },
            "required": ["command"],
        },
    },
    "file": {
        "description": "Perform file operations (read, write, list, etc.)",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["read", "write", "append", "delete", "list", "exists"],
                    "description": "The file action to perform",
                },
                "path": {
                    "type": "string",
                    "description": "Path to the file or directory",
                },
                "content": {
                    "type": "string",
                    "description": "Content to write (for write/append actions)",
                },
            },
            "required": ["action", "path"],
        },
    },
    "http": {
        "description": "Make HTTP requests to fetch data from URLs",
        "parameters": {
            "type": "object",
            "properties": {
                "method": {
                    "type": "string",
                    "enum": [
                        "GET",
                        "POST",
                        "PUT",
                        "PATCH",
                        "DELETE",
                        "HEAD",
                        "OPTIONS",
                    ],
                    "description": "HTTP method",
                },
                "url": {
                    "type": "string",
                    "description": "The URL to request",
                },
                "headers": {
                    "type": "object",
                    "description": "Optional HTTP headers as key-value pairs",
                },
                "body": {
                    "type": "object",
                    "description": "Request body for POST/PUT/PATCH",
                },
                "timeout": {
                    "type": "number",
                    "description": "Request timeout in seconds (default: 10)",
                },
            },
            "required": ["method", "url"],
        },
    },
}


class OpenAIToolCallParser(ToolCallParser):
    """Parser for OpenAI function calling format."""

    def parse(self, text: str) -> list[dict[str, Any]]:
        """
        Parse OpenAI-style tool calls from LLM output.

        Expected format:
        {
            "tool_calls": [
                {
                    "id": "call_abc123",
                    "type": "function",
                    "function": {
                        "name": "http_request",
                        "arguments": "{\"method\": \"GET\", \"url\": \"...\"}"
                    }
                }
            ]
        }

        Also supports legacy format for backwards compatibility:
        {"tool": "http", "method": "GET", "url": "..."}
        """
        tool_calls = []

        # Try to find JSON object with tool_calls array
        try:
            # Look for the tool_calls structure
            for line in text.split("\n"):
                stripped = line.strip()
                if not stripped:
                    continue

                try:
                    parsed = json.loads(stripped)
                except json.JSONDecodeError:
                    continue

                # Check for OpenAI format
                if isinstance(parsed, dict):
                    if "tool_calls" in parsed and isinstance(
                        parsed["tool_calls"], list
                    ):
                        for tc in parsed["tool_calls"]:
                            if isinstance(tc, dict):
                                func = tc.get("function", {})
                                if func:
                                    tool_calls.append(
                                        {
                                            "id": tc.get(
                                                "id", f"call_{len(tool_calls)}"
                                            ),
                                            "type": tc.get("type", "function"),
                                            "name": func.get("name", ""),
                                            "arguments": func.get("arguments", "{}"),
                                        }
                                    )

                    # Check for legacy format (for backwards compatibility)
                    elif "tool" in parsed:
                        tool_calls.append(
                            {
                                "id": f"call_{len(tool_calls)}",
                                "type": "function",
                                "name": f"{parsed['tool']}_request",
                                "arguments": json.dumps(
                                    {k: v for k, v in parsed.items() if k != "tool"}
                                ),
                            }
                        )

        except Exception:
            pass

        # If no structured JSON found, try to find JSON objects with tool key
        if not tool_calls:
            tool_calls = self._parse_legacy_format(text)

        return tool_calls

    def _parse_legacy_format(self, text: str) -> list[dict[str, Any]]:
        """Parse legacy format as fallback."""
        tool_calls = []

        # Pattern to match JSON objects with "tool" key
        pattern = r'\{\s*"tool"\s*:\s*"(\w+)"[^}]*\}'

        for match in re.finditer(pattern, text):
            try:
                obj = json.loads(match.group())
                if "tool" in obj:
                    args = {k: v for k, v in obj.items() if k != "tool"}
                    tool_calls.append(
                        {
                            "id": f"call_{len(tool_calls)}",
                            "type": "function",
                            "name": f"{obj['tool']}_request",
                            "arguments": json.dumps(args),
                        }
                    )
            except json.JSONDecodeError:
                continue

        return tool_calls

    def format_tools_for_prompt(self, tools: list[str] | None = None) -> str:
        """
        Format tools as OpenAI function definitions for the prompt.

        Uses JSON Schema format that OpenAI-style models expect.
        """
        if tools is None:
            tools = list(TOOL_DEFINITIONS.keys())

        tool_definitions = []

        for tool_name in tools:
            if tool_name in TOOL_DEFINITIONS:
                definition = TOOL_DEFINITIONS[tool_name]
                tool_definitions.append(
                    {
                        "type": "function",
                        "function": {
                            "name": f"{tool_name}_request",
                            "description": definition["description"],
                            "parameters": definition["parameters"],
                        },
                    }
                )

        if not tool_definitions:
            return ""

        return json.dumps(tool_definitions, indent=2)

    def format_tools_for_prompt_list(self) -> list[dict[str, Any]]:
        """Return tool definitions as a list for LLM API calls."""
        tool_definitions = []

        for tool_name, definition in TOOL_DEFINITIONS.items():
            tool_definitions.append(
                {
                    "type": "function",
                    "function": {
                        "name": f"{tool_name}_request",
                        "description": definition["description"],
                        "parameters": definition["parameters"],
                    },
                }
            )

        return tool_definitions
