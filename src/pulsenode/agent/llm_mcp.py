from dataclasses import dataclass
from typing import Any
from pydantic import BaseModel
import httpx
import json

from pulsenode.config.settings import settings


class TriageResponse(BaseModel):
    needed: bool
    reason: str


@dataclass(frozen=True)
class LlmMcp:
    mcp_url: str
    auth_token: str
    max_tokens: int

    async def generate_triage_response(self, prompt: str) -> TriageResponse:
        """Generate a triage response to determine if action is needed."""
        if not settings.llm_proxy.enabled:
            # Mock implementation when proxy is disabled
            return TriageResponse(
                needed=True, reason="Mock reason - LLM proxy disabled"
            )

        try:
            # Call the llm_proxy_mcp tool for generation
            messages = [
                {
                    "role": "user",
                    "content": f"Determine if this message needs action: {prompt}",
                }
            ]

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.mcp_url}/llm/llm_chat",
                    headers={"Authorization": f"Bearer {self.auth_token}"},
                    json={
                        "messages": messages,
                        "provider": settings.llm_proxy.provider,
                        "model": settings.llm_proxy.model,
                        "temperature": 0.3,
                        "max_tokens": 100,
                        "stream": False,
                    },
                    timeout=30.0,
                )
                response.raise_for_status()
                result = response.json()

                # Parse the response to determine if action is needed
                content = result.get("content", "").lower()
                needed = "yes" in content or "action" in content or "needed" in content

                return TriageResponse(needed=needed, reason=result.get("content", ""))

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
            messages = [{"role": "user", "content": prompt}]

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.mcp_url}/llm/llm_chat",
                    headers={"Authorization": f"Bearer {self.auth_token}"},
                    json={
                        "messages": messages,
                        "provider": settings.llm_proxy.provider,
                        "model": settings.llm_proxy.model,
                        "temperature": settings.llm_proxy.temperature,
                        "max_tokens": self.max_tokens,
                        "stream": False,
                    },
                    timeout=60.0,
                )
                response.raise_for_status()
                result = response.json()

                return result.get("content", "No response generated")

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
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.mcp_url}/llm/llm_chat",
                    headers={"Authorization": f"Bearer {self.auth_token}"},
                    json={
                        "messages": messages,
                        "provider": provider or settings.llm_proxy.provider,
                        "model": model or settings.llm_proxy.model,
                        "temperature": temperature or settings.llm_proxy.temperature,
                        "max_tokens": max_tokens or self.max_tokens,
                        "stream": False,
                    },
                    timeout=60.0,
                )
                response.raise_for_status()
                result = response.json()

                return result.get("content", "No response generated")

        except Exception as e:
            return f"Error in chat: {str(e)}"

    async def list_available_models(
        self, provider: str | None = None
    ) -> list[dict[str, Any]]:
        """List available models from the LLM provider."""
        if not settings.llm_proxy.enabled:
            return []

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.mcp_url}/llm/llm_list_models",
                    headers={"Authorization": f"Bearer {self.auth_token}"},
                    json={"provider": provider or settings.llm_proxy.provider},
                    timeout=10.0,
                )
                response.raise_for_status()
                result = response.json()

                return result.get("result", [])

        except Exception as e:
            return [{"error": str(e)}]

    async def switch_llm_model(
        self, model: str, provider: str | None = None
    ) -> dict[str, Any]:
        """Switch to a different model."""
        if not settings.llm_proxy.enabled:
            return {"error": "LLM proxy is disabled"}

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.mcp_url}/llm/llm_switch_model",
                    headers={"Authorization": f"Bearer {self.auth_token}"},
                    json={
                        "model": model,
                        "provider": provider or settings.llm_proxy.provider,
                    },
                    timeout=10.0,
                )
                response.raise_for_status()
                return response.json()

        except Exception as e:
            return {"error": str(e)}
