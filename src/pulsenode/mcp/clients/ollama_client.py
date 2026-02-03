import httpx
import json
from typing import Any, AsyncGenerator
from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    stream: bool | None = True
    options: dict[str, Any] | None = None


class ChatResponse(BaseModel):
    id: str
    object: str
    created: int
    model: str
    choices: list[dict[str, Any]]
    usage: dict[str, int] | None = None


class OllamaClient:
    def __init__(self, endpoint: str, model: str, api_key: str | None = None):
        self.base_url = f"{endpoint.rstrip('/')}/api"
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
        Send chat messages to Ollama and stream responses.
        """
        request_data = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            "options": {"temperature": temperature},
        }
        if max_tokens:
            request_data["options"]["max_tokens"] = max_tokens

        self.metrics["requests"] += 1

        try:
            async with self.session.stream(
                "POST",
                f"{self.base_url}/chat",
                json=request_data,
                headers=self._get_headers(),
            ) as response:
                async for line in response.aiter_lines():
                    if line.strip():
                        try:
                            chunk = json.loads(line)
                            # Update metrics
                            if "message" in chunk and "content" in chunk["message"]:
                                self.metrics["tokens_generated"] += len(
                                    chunk["message"]["content"].split()
                                )

                            yield chunk
                        except json.JSONDecodeError:
                            # Skip invalid JSON lines
                            continue

        except Exception as e:
            self.metrics["errors"] += 1
            raise Exception(f"Ollama request failed: {str(e)}")

    async def generate(
        self,
        prompt: str,
        stream: bool = True,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """
        Generate text using Ollama (simplified chat interface)
        """
        messages = [{"role": "user", "content": prompt}]
        return self.chat(messages, stream, temperature, max_tokens)

    async def list_models(self) -> list[dict[str, Any]]:
        """List available models from Ollama"""
        try:
            response = await self.session.get(
                f"{self.base_url}/tags", headers=self._get_headers()
            )
            response.raise_for_status()
            data = response.json()
            return data.get("models", [])
        except Exception as e:
            raise Exception(f"Failed to list models: {str(e)}")

    async def switch_model(self, model: str) -> dict[str, Any]:
        """Switch to a different model"""
        self.model = model
        return {"model": self.model, "status": "switched"}

    def get_metrics(self) -> dict[str, Any]:
        """Get performance metrics"""
        return self.metrics.copy()

    async def close(self):
        """Close the HTTP client"""
        await self.session.aclose()
