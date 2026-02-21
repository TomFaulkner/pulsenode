import httpx
import json
import asyncio
from typing import Any, AsyncGenerator
from pydantic import BaseModel
from structlog import get_logger

logger = get_logger(__name__)


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
    def __init__(
        self,
        endpoint: str,
        model: str,
        api_key: str | None = None,
        read_timeout: float = 30.0,
        connect_timeout: float = 10.0,
        write_timeout: float = 10.0,
        max_retries: int = 3,
        retry_backoff_factor: float = 2.0,
    ):
        self.base_url = f"{endpoint.rstrip('/')}/api"
        self.model = model
        self.api_key = api_key
        self.read_timeout = read_timeout
        self.connect_timeout = connect_timeout
        self.write_timeout = write_timeout
        self.max_retries = max_retries
        self.retry_backoff_factor = retry_backoff_factor

        self.session = httpx.AsyncClient(
            timeout=httpx.Timeout(
                read=read_timeout,
                connect=connect_timeout,
                write=write_timeout,
                pool=None,  # Use default for pool timeout
            )
        )
        self.metrics = {
            "requests": 0,
            "errors": 0,
            "timeouts": 0,
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
        read_timeout: float | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """
        Send chat messages to Ollama and stream responses.

        Args:
            messages: List of message dicts with 'role' and 'content' keys
            stream: Whether to stream the response
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            read_timeout: Custom read timeout
            tools: List of tool definitions in OpenAI format
        """
        request_data = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            "options": {"temperature": temperature},
        }
        if max_tokens:
            request_data["options"]["max_tokens"] = max_tokens
        if tools:
            request_data["tools"] = tools

        self.metrics["requests"] += 1

        # Use custom timeout if provided, otherwise use instance default
        timeout = read_timeout if read_timeout is not None else self.read_timeout

        for attempt in range(self.max_retries + 1):
            try:
                async with self.session.stream(
                    "POST",
                    f"{self.base_url}/chat",
                    json=request_data,
                    headers=self._get_headers(),
                    timeout=httpx.Timeout(
                        read=timeout,
                        connect=self.connect_timeout,
                        write=self.write_timeout,
                        pool=None,
                    ),
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
                    break  # Success, exit retry loop

            except httpx.ReadTimeout as e:
                self.metrics["timeouts"] += 1
                if attempt == self.max_retries:
                    logger.error(
                        "ollama_read_timeout_final",
                        model=self.model,
                        timeout=timeout,
                        attempts=attempt + 1,
                        error=str(e),
                    )
                    self.metrics["errors"] += 1
                    raise Exception(
                        f"Ollama read timeout after {self.max_retries + 1} attempts: {str(e)}"
                    )

                # Log retry attempt
                backoff_delay = self.retry_backoff_factor**attempt
                logger.warning(
                    "ollama_read_timeout_retrying",
                    model=self.model,
                    timeout=timeout,
                    attempt=attempt + 1,
                    max_retries=self.max_retries + 1,
                    backoff_delay=backoff_delay,
                    error=str(e),
                )
                await asyncio.sleep(backoff_delay)

            except httpx.ConnectTimeout as e:
                self.metrics["timeouts"] += 1
                if attempt == self.max_retries:
                    logger.error(
                        "ollama_connect_timeout_final",
                        model=self.model,
                        timeout=self.connect_timeout,
                        attempts=attempt + 1,
                        error=str(e),
                    )
                    self.metrics["errors"] += 1
                    raise Exception(
                        f"Ollama connect timeout after {self.max_retries + 1} attempts: {str(e)}"
                    )

                backoff_delay = self.retry_backoff_factor**attempt
                logger.warning(
                    "ollama_connect_timeout_retrying",
                    model=self.model,
                    timeout=self.connect_timeout,
                    attempt=attempt + 1,
                    max_retries=self.max_retries + 1,
                    backoff_delay=backoff_delay,
                    error=str(e),
                )
                await asyncio.sleep(backoff_delay)

            except Exception as e:
                self.metrics["errors"] += 1
                logger.error(
                    "ollama_request_error",
                    model=self.model,
                    attempt=attempt + 1,
                    error=str(e),
                    error_type=type(e).__name__,
                )
                raise Exception(f"Ollama request failed: {str(e)}")

    async def generate(
        self,
        prompt: str,
        stream: bool = True,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """
        Generate text using Ollama (simplified chat interface)
        """
        messages = [{"role": "user", "content": prompt}]
        return self.chat(messages, stream, temperature, max_tokens, tools=tools)

    async def list_models(self) -> list[dict[str, Any]]:
        """List available models from Ollama"""
        for attempt in range(self.max_retries + 1):
            try:
                response = await self.session.get(
                    f"{self.base_url}/tags",
                    headers=self._get_headers(),
                    timeout=httpx.Timeout(
                        read=self.read_timeout,
                        connect=self.connect_timeout,
                        write=self.write_timeout,
                        pool=None,
                    ),
                )
                response.raise_for_status()
                data = response.json()
                return data.get("models", [])

            except httpx.ReadTimeout as e:
                self.metrics["timeouts"] += 1
                if attempt == self.max_retries:
                    logger.error(
                        "ollama_list_models_read_timeout",
                        timeout=self.read_timeout,
                        attempts=attempt + 1,
                        error=str(e),
                    )
                    raise Exception(
                        f"Failed to list models due to read timeout: {str(e)}"
                    )

                backoff_delay = self.retry_backoff_factor**attempt
                await asyncio.sleep(backoff_delay)

            except httpx.ConnectTimeout as e:
                self.metrics["timeouts"] += 1
                if attempt == self.max_retries:
                    logger.error(
                        "ollama_list_models_connect_timeout",
                        timeout=self.connect_timeout,
                        attempts=attempt + 1,
                        error=str(e),
                    )
                    raise Exception(
                        f"Failed to list models due to connect timeout: {str(e)}"
                    )

                backoff_delay = self.retry_backoff_factor**attempt
                await asyncio.sleep(backoff_delay)

            except Exception as e:
                logger.error(
                    "ollama_list_models_error",
                    attempt=attempt + 1,
                    error=str(e),
                    error_type=type(e).__name__,
                )
                raise Exception(f"Failed to list models: {str(e)}")

        # This should never be reached due to exceptions in retry loop
        raise Exception("Failed to list models: unexpected code path")

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
