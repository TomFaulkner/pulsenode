from dataclasses import dataclass
from typing import Any, cast
from pydantic import BaseModel
import httpx
import json

import structlog

from pulsenode.config.settings import settings

logger: structlog.BoundLogger = cast(
    "structlog.BoundLogger", structlog.get_logger(__name__).bind(module=__name__)
)


class TriageResponse(BaseModel):
    needed: bool
    reason: str


@dataclass
class LlmMcp:
    mcp_url: str
    auth_token: str
    max_tokens: int
    session_id: str = ""
    provider: str = "ollama"
    model: str = "llama3"
    temperature: float = 0.7
    triage_max_tokens: int = 100
    triage_temperature: float = 0.3

    def __post_init__(self):
        if self.temperature > 1.0 or self.temperature < 0.0:
            raise ValueError("Temperature must be between 0.0 and 1.0")

    async def _ensure_session_initialized(self) -> str:
        """Initialize MCP session if not already done."""
        if self.session_id:
            return self.session_id

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.mcp_url}",
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {
                            "roots": {"listChanged": True},
                            "sampling": {},
                        },
                        "clientInfo": {"name": "pulsenode", "version": "1.0"},
                    },
                    "id": "init",
                },
            )
            _ = response.raise_for_status()

            # Extract session ID from response headers
            session_id = self._extract_session_id(response.headers)
            if session_id:
                self.__dict__["session_id"] = session_id
                return session_id
            else:
                raise Exception(
                    "Failed to initialize MCP session - no session ID returned"
                )

    def _parse_sse_response(self, response_text: str) -> dict:
        """Parse Server-Sent Events response to extract JSON data."""
        for line in response_text.split("\n"):
            if line.startswith("data: "):
                try:
                    return json.loads(line[6:])
                except json.JSONDecodeError:
                    continue
        return {}

    def _extract_session_id(self, headers: dict[str, str] | httpx.Headers) -> str:
        """Extract session ID from response headers."""
        return headers.get("mcp-session-id", "")

    async def generate_triage_response(self, prompt: str) -> TriageResponse:
        """Generate a triage response to determine if action is needed."""
        if not settings.llm_proxy.enabled:
            # Mock implementation when proxy is disabled
            return TriageResponse(
                needed=True, reason="Mock reason - LLM proxy disabled"
            )

        try:
            # Ensure session is initialized
            session_id = await self._ensure_session_initialized()

            # Call the llm_proxy_mcp tool for generation
            messages = [
                {
                    "role": "user",
                    "content": f"Determine if this message needs action: {prompt}",
                }
            ]

            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "mcp-session-id": session_id,
            }
            if self.auth_token:
                headers["Authorization"] = f"Bearer {self.auth_token}"

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.mcp_url}",
                    headers=headers,
                    json={
                        "jsonrpc": "2.0",
                        "method": "tools/call",
                        "params": {
                            "name": "llm_llm_chat",
                            "arguments": {
                                "request": {
                                    "messages": messages,
                                    "provider": self.provider,
                                    "model": self.model,
                                    "temperature": self.triage_temperature,
                                    "max_tokens": self.triage_max_tokens,
                                    "stream": False,
                                }
                            },
                        },
                        "id": "triage-req-001",
                    },
                    timeout=30.0,
                )
                _ = response.raise_for_status()

                # Handle SSE response
                result = self._parse_sse_response(response.text)

                # Check for error in result
                if "error" in result:
                    raise Exception(f"MCP Error: {result['error']}")

                result_data = result.get("result", {})
                content = result_data.get("content", [])

                # Extract text from content array
                text_content = ""
                if isinstance(content, list) and content:
                    if content[0].get("type") == "text":
                        text_content = content[0].get("text", "")
                elif isinstance(content, str):
                    text_content = content
                else:
                    text_content = str(result_data) or ""

                # Parse the response to determine if action is needed
                content_lower = text_content.lower()
                needed = (
                    "yes" in content_lower
                    or "action" in content_lower
                    or "needed" in content_lower
                )

                logger.debug("triage_response", needed=needed, reason=text_content)
                return TriageResponse(needed=needed, reason=text_content)

        except Exception as e:
            # Fallback to mock on error
            return TriageResponse(
                needed=True,
                reason=f"Error calling LLM proxy: {str(e)}. Defaulting to action needed.",
            )

    async def generate_response(self, prompt: str) -> str:
        """Generate a response using the LLM proxy."""
        if not settings.llm_proxy.enabled:
            # Mock implementation when proxy is disabled
            return f"Mock response: {prompt[:50]}..."

        try:
            # Ensure session is initialized
            session_id = await self._ensure_session_initialized()

            messages = [{"role": "user", "content": prompt}]

            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "mcp-session-id": session_id,
            }
            if self.auth_token:
                headers["Authorization"] = f"Bearer {self.auth_token}"

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.mcp_url}",
                    headers=headers,
                    json={
                        "jsonrpc": "2.0",
                        "method": "tools/call",
                        "params": {
                            "name": "llm_llm_chat",
                            "arguments": {
                                "request": {
                                    "messages": messages,
                                    "provider": self.provider,
                                    "model": self.model,
                                    "temperature": self.temperature,
                                    "max_tokens": self.max_tokens,
                                    "stream": False,
                                }
                            },
                        },
                        "id": "generate-req-001",
                    },
                    timeout=60.0,
                )
                response.raise_for_status()

                # Handle SSE response
                result = self._parse_sse_response(response.text)

                # Check for error in result
                if "error" in result:
                    raise Exception(f"MCP Error: {result['error']}")

                result_data = result.get("result", {})
                content = result_data.get("content", [])

                # Extract text from content array if needed
                if isinstance(content, list) and content:
                    if content[0].get("type") == "text":
                        return content[0].get("text", "No response generated")
                elif isinstance(content, str):
                    return content

                return str(result_data) or "No response generated"

        except Exception as e:
            return f"Error generating response: {str(e)}"

    async def chat_with_llm(
        self,
        messages: list[dict[str, str]],
        provider: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """
        Chat with LLM through the proxy with full control over parameters.

        Args:
            messages: list of message dicts with 'role' and 'content'
            provider: LLM provider (ollama or llamacpp)
            model: Specific model to use
            temperature: Generation temperature
            max_tokens: Max tokens to generate

        Returns:
            Response content from the LLM
        """
        if not settings.llm_proxy.enabled:
            return "LLM proxy is disabled. Enable it in settings to use this feature."

        try:
            # Ensure session is initialized
            session_id = await self._ensure_session_initialized()

            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "mcp-session-id": session_id,
            }
            if self.auth_token:
                headers["Authorization"] = f"Bearer {self.auth_token}"

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.mcp_url}",
                    headers=headers,
                    json={
                        "jsonrpc": "2.0",
                        "method": "tools/call",
                        "params": {
                            "name": "llm_llm_chat",
                            "arguments": {
                                "request": {
                                    "messages": messages,
                                    "provider": provider or self.provider,
                                    "model": model or self.model,
                                    "temperature": temperature
                                    or settings.llm_proxy.temperature,
                                    "max_tokens": max_tokens or self.max_tokens,
                                    "stream": False,
                                }
                            },
                        },
                        "id": "chat-req-001",
                    },
                    timeout=60.0,
                )
                response.raise_for_status()

                # Handle SSE response
                result = self._parse_sse_response(response.text)

                # Check for error in result
                if "error" in result:
                    raise Exception(f"MCP Error: {result['error']}")

                result_data = result.get("result", {})
                content = result_data.get("content", [])

                # Extract text from content array
                if isinstance(content, list) and content:
                    if content[0].get("type") == "text":
                        return content[0].get("text", "No response generated")
                elif isinstance(content, str):
                    return content

                return str(result_data) or "No response generated"

        except Exception as e:
            return f"Error in chat: {str(e)}"

    async def list_available_models(
        self, provider: str | None = None
    ) -> list[dict[str, Any]]:
        """List available models from the LLM provider."""
        if not settings.llm_proxy.enabled:
            return []

        try:
            # Ensure session is initialized
            session_id = await self._ensure_session_initialized()

            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "mcp-session-id": session_id,
            }
            if self.auth_token:
                headers["Authorization"] = f"Bearer {self.auth_token}"

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.mcp_url}",
                    headers=headers,
                    json={
                        "jsonrpc": "2.0",
                        "method": "tools/call",
                        "params": {
                            "name": "llm_llm_list_models",
                            "arguments": {
                                "provider": provider or self.provider,
                            },
                        },
                        "id": "list-models-req-001",
                    },
                    timeout=10.0,
                )
                response.raise_for_status()

                # Handle SSE response
                result = self._parse_sse_response(response.text)

                # Check for error in result
                if "error" in result:
                    raise Exception(f"MCP Error: {result['error']}")

                result_data = result.get("result", {})
                content = result_data.get("content", [])

                # Extract models from content array
                if (
                    isinstance(content, list)
                    and content
                    and content[0].get("type") == "text"
                ):
                    try:
                        # Try to parse the text as JSON
                        models_text = content[0].get("text", "[]")
                        return json.loads(models_text)
                    except json.JSONDecodeError:
                        return [{"error": f"Failed to parse models: {models_text}"}]
                elif isinstance(content, str):
                    try:
                        return json.loads(content)
                    except json.JSONDecodeError:
                        return [{"error": f"Failed to parse models: {content}"}]

                return result_data.get("result", [])  # Fallback

        except Exception as e:
            return [{"error": str(e)}]

    async def switch_llm_model(
        self, model: str, provider: str | None = None
    ) -> dict[str, Any]:
        """Switch to a different model."""
        if not settings.llm_proxy.enabled:
            return {"error": "LLM proxy is disabled"}

        try:
            # Ensure session is initialized
            session_id = await self._ensure_session_initialized()

            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "mcp-session-id": session_id,
            }
            if self.auth_token:
                headers["Authorization"] = f"Bearer {self.auth_token}"

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.mcp_url}",
                    headers=headers,
                    json={
                        "jsonrpc": "2.0",
                        "method": "tools/call",
                        "params": {
                            "name": "llm_llm_switch_model",
                            "arguments": {
                                "model": model,
                                "provider": provider or self.provider,
                            },
                        },
                        "id": "switch-model-req-001",
                    },
                    timeout=10.0,
                )
                response.raise_for_status()

                # Handle SSE response
                result = self._parse_sse_response(response.text)

                # Check for error in result
                if "error" in result:
                    raise Exception(f"MCP Error: {result['error']}")

                result_data = result.get("result", {})
                content = result_data.get("content", [])

                # Extract result from content array
                if (
                    isinstance(content, list)
                    and content
                    and content[0].get("type") == "text"
                ):
                    try:
                        result_text = content[0].get("text", "{}")
                        return json.loads(result_text)
                    except json.JSONDecodeError:
                        return {"result": result_text}
                elif isinstance(content, str):
                    try:
                        return json.loads(content)
                    except json.JSONDecodeError:
                        return {"result": content}

                return result_data.get("result", {})  # Fallback

        except Exception as e:
            return {"error": str(e)}
