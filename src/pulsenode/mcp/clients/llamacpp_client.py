import httpx
import json
from typing import Any, AsyncGenerator
from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: str
    content: str


class LlamaCppRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    stream: bool = True
    temperature: float | None = 0.7
    max_tokens: int | None = None


class LlamaCppClient:
    """Client for llama.cpp OpenAI-compatible API"""

    def __init__(self, endpoint: str, model: str, api_key: str | None = None):
        self.base_url = endpoint.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.session = httpx.AsyncClient()
        self.metrics = {
            "requests": 0,
            "errors": 0,
            "total_duration": 0,
            "tokens_generated": 0,
        }

    def _get_headers(self) -> dict[str, str]:
        """Get headers including authentication if needed"""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def chat(
        self,
        messages: list[dict[str, str]],
        stream: bool = True,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """
        Send chat messages to llama.cpp server and stream responses.
        """
        request_data = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            "temperature": temperature,
        }
        if max_tokens:
            request_data["max_tokens"] = max_tokens

        self.metrics["requests"] += 1

        try:
            async with self.session.stream(
                "POST",
                f"{self.base_url}/v1/chat/completions",
                json=request_data,
                headers=self._get_headers(),
            ) as response:
                async for line in response.aiter_lines():
                    if line.strip() and line.startswith("data: "):
                        try:
                            chunk = json.loads(line[6:])  # Remove "data: " prefix
                            # Update metrics
                            if "choices" in chunk and chunk["choices"]:
                                choice = chunk["choices"][0]
                                if "delta" in choice and "content" in choice["delta"]:
                                    self.metrics["tokens_generated"] += len(
                                        choice["delta"]["content"].split()
                                    )

                            yield chunk
                        except json.JSONDecodeError:
                            # Skip invalid JSON lines
                            continue

        except Exception as e:
            self.metrics["errors"] += 1
            raise Exception(f"llama.cpp request failed: {str(e)}")

    async def generate(
        self,
        prompt: str,
        stream: bool = True,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """
        Generate text using llama.cpp (simplified chat interface)
        """
        messages = [{"role": "user", "content": prompt}]
        return self.chat(messages, stream, temperature, max_tokens)

    async def list_models(self) -> list[dict[str, Any]]:
        """
        List available models from llama.cpp.
        Note: llama.cpp typically loads only one model, so we return current model info.
        """
        return [{"name": self.model, "provider": "llamacpp"}]

    async def switch_model(self, model: str) -> dict[str, Any]:
        """Switch to a different model (requires llama.cpp restart for different model)"""
        self.model = model
        return {
            "model": self.model,
            "status": "switched",
            "note": "Model switch requires llama.cpp server restart for different GGUF files",
        }

    def get_metrics(self) -> dict[str, Any]:
        """Get performance metrics"""
        return self.metrics.copy()

    async def close(self):
        """Close the HTTP client"""
        await self.session.aclose()
