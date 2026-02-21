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


class LlamaCppRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    stream: bool = True
    temperature: float | None = 0.7
    max_tokens: int | None = None


class LlamaCppClient:
    """Client for llama.cpp OpenAI-compatible API"""

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
        self.base_url = endpoint.rstrip("/")
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
        Send chat messages to llama.cpp server and stream responses.

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
            "temperature": temperature,
        }
        if max_tokens:
            request_data["max_tokens"] = max_tokens
        if tools:
            request_data["tools"] = tools

        self.metrics["requests"] += 1

        # Use custom timeout if provided, otherwise use instance default
        timeout = read_timeout if read_timeout is not None else self.read_timeout

        for attempt in range(self.max_retries + 1):
            try:
                async with self.session.stream(
                    "POST",
                    f"{self.base_url}/v1/chat/completions",
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
                        if line.strip() and line.startswith("data: "):
                            try:
                                chunk = json.loads(line[6:])  # Remove "data: " prefix
                                # Update metrics
                                if "choices" in chunk and chunk["choices"]:
                                    choice = chunk["choices"][0]
                                    if (
                                        "delta" in choice
                                        and "content" in choice["delta"]
                                    ):
                                        self.metrics["tokens_generated"] += len(
                                            choice["delta"]["content"].split()
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
                        "llamacpp_read_timeout_final",
                        model=self.model,
                        timeout=timeout,
                        attempts=attempt + 1,
                        error=str(e),
                    )
                    self.metrics["errors"] += 1
                    raise Exception(
                        f"llama.cpp read timeout after {self.max_retries + 1} attempts: {str(e)}"
                    )

                # Log retry attempt
                backoff_delay = self.retry_backoff_factor**attempt
                logger.warning(
                    "llamacpp_read_timeout_retrying",
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
                        "llamacpp_connect_timeout_final",
                        model=self.model,
                        timeout=self.connect_timeout,
                        attempts=attempt + 1,
                        error=str(e),
                    )
                    self.metrics["errors"] += 1
                    raise Exception(
                        f"llama.cpp connect timeout after {self.max_retries + 1} attempts: {str(e)}"
                    )

                backoff_delay = self.retry_backoff_factor**attempt
                logger.warning(
                    "llamacpp_connect_timeout_retrying",
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
                    "llamacpp_request_error",
                    model=self.model,
                    attempt=attempt + 1,
                    error=str(e),
                    error_type=type(e).__name__,
                )
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
