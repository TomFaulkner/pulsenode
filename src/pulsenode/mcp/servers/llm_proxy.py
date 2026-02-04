import json
import time
from typing import Any, AsyncGenerator
from pydantic import BaseModel, Field
from fastmcp import FastMCP, Context
from structlog import get_logger

from pulsenode.config.settings import settings
from pulsenode.mcp.clients.ollama_client import OllamaClient
from pulsenode.mcp.clients.llamacpp_client import LlamaCppClient


logger = get_logger(__name__)


class ChatMessage(BaseModel):
    role: str
    content: str


class LLMRequest(BaseModel):
    provider: str | None = None
    model: str | None = None
    messages: list[dict[str, str]]
    stream: bool = True
    temperature: float = Field(0.7, ge=0.0, le=1.0)
    max_tokens: int | None = None


class LLMResponse(BaseModel):
    content: str
    model: str
    provider: str
    tokens_used: int | None = None
    duration_ms: float | None = None


class LLMProxyServer:
    """MCP Server that proxies calls to LLM providers (Ollama and llama.cpp)"""

    def __init__(self):
        self.clients = {}
        self.metrics = {
            "requests": 0,
            "errors": 0,
            "total_latency": 0.0,
            "total_tokens": 0,
        }

        # Initialize clients for both providers
        if settings.llm_proxy.enabled:
            self._init_clients()

    def _init_clients(self):
        """Initialize clients for configured providers"""
        logger.info("Initializing LLM proxy clients")

        # Ollama client (default)
        self.clients["ollama"] = OllamaClient(
            endpoint=settings.llm_proxy.endpoint,
            model=settings.llm_proxy.model,
            api_key=settings.llm_proxy.api_key,
        )

        # Llama.cpp client (if different endpoint configured)
        llamacpp_endpoint = getattr(settings.llm_proxy, "llamacpp_endpoint", None)
        if llamacpp_endpoint:
            self.clients["llamacpp"] = LlamaCppClient(
                endpoint=llamacpp_endpoint,
                model=settings.llm_proxy.model,
                api_key=settings.llm_proxy.api_key,
            )

        logger.info(f"Initialized {len(self.clients)} LLM clients")

    def get_client(self, provider: str | None = None) -> OllamaClient | LlamaCppClient:
        """Get client for specified provider or default"""
        provider = provider or settings.llm_proxy.provider_default

        if provider not in self.clients:
            raise Exception(f"Provider {provider} not configured or not available")

        return self.clients[provider]

    async def chat(
        self,
        messages: list[dict[str, str]],
        provider: str | None = None,
        model: str | None = None,
        stream: bool = True,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Chat with LLM provider"""
        client = self.get_client(provider)
        provider_name = provider or settings.llm_proxy.provider_default

        # Temporarily switch model if requested
        if model and model != client.model:
            await client.switch_model(model)

        start_time = time.time()
        self.metrics["requests"] += 1

        try:
            async for chunk in client.chat(
                messages=messages,
                stream=stream,
                temperature=temperature,
                max_tokens=max_tokens,
            ):
                yield chunk

            # Update metrics
            duration = time.time() - start_time
            self.metrics["total_latency"] += duration

        except Exception as e:
            self.metrics["errors"] += 1
            logger.error("llm_proxy_chat_error", provider=provider_name, error=str(e))
            raise

    async def generate(
        self,
        prompt: str,
        provider: str | None = None,
        model: str | None = None,
        stream: bool = True,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Generate text from LLM provider"""
        messages = [{"role": "user", "content": prompt}]
        async for chunk in self.chat(
            messages=messages,
            provider=provider,
            model=model,
            stream=stream,
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            yield chunk

    async def list_models(self, provider: str | None = None) -> list[dict[str, Any]]:
        """List available models from specified provider"""
        client = self.get_client(provider)
        return await client.list_models()

    async def switch_model(
        self, model: str, provider: str | None = None
    ) -> dict[str, Any]:
        """Switch to a different model"""
        client = self.get_client(provider)
        result = await client.switch_model(model)
        logger.info(
            "llm_model_switched",
            provider=provider or settings.llm_proxy.provider_default,
            model=model,
        )
        return result

    def get_metrics(self) -> dict[str, Any]:
        """Get performance metrics"""
        avg_latency = (
            self.metrics["total_latency"] / self.metrics["requests"]
            if self.metrics["requests"] > 0
            else 0
        )

        return {
            "requests": self.metrics["requests"],
            "errors": self.metrics["errors"],
            "error_rate": (
                self.metrics["errors"] / self.metrics["requests"] * 100
                if self.metrics["requests"] > 0
                else 0
            ),
            "average_latency_ms": round(avg_latency * 1000, 2),
            "total_latency_ms": round(self.metrics["total_latency"] * 1000, 2),
        }

    async def close(self):
        """Close all client connections"""
        for client in self.clients.values():
            await client.close()


# Create the MCP Server using composition
llm_proxy_mcp = FastMCP(
    "llm-proxy",
    instructions="Proxy server for LLM providers (Ollama and llama.cpp). Supports chat, generation, model management, and streaming.",
)

# Initialize server instance
llm_server = LLMProxyServer()


@llm_proxy_mcp.tool()
async def llm_chat(request: LLMRequest, ctx: Context) -> str:
    """
    Chat with an LLM provider. Supports Ollama and llama.cpp.

    Args:
        request: Chat request with messages, provider selection, and generation parameters

    Returns:
        Response from the LLM provider
    """
    logger.info(
        "llm_chat_request",
        provider=request.provider or settings.llm_proxy.provider_default,
        model=request.model or settings.llm_proxy.model,
        num_messages=len(request.messages),
    )

    full_response = []

    async for chunk in llm_server.chat(
        messages=request.messages,
        provider=request.provider,
        model=request.model,
        stream=request.stream,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
    ):
        # Extract content based on provider format
        if "message" in chunk:
            content = chunk["message"].get("content", "")
        elif "choices" in chunk:
            content = chunk["choices"][0].get("delta", {}).get("content", "")
        else:
            content = str(chunk)

        full_response.append(content)

        # Stream to client if supported
        if request.stream:
            await ctx.info(content)

    return "".join(full_response)


@llm_proxy_mcp.tool()
async def llm_generate(
    prompt: str,
    provider: str | None = None,
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int | None = None,
    stream: bool = True,
) -> str:
    """
    Generate text from an LLM provider based on a prompt.

    Args:
        prompt: The text prompt to generate from
        provider: LLM provider (ollama or llamacpp)
        model: Specific model to use
        temperature: Generation temperature (0.0-1.0)
        max_tokens: Maximum tokens to generate
        stream: Whether to stream the response

    Returns:
        Generated text from the LLM provider
    """
    logger.info(
        "llm_generate_request",
        provider=provider or settings.llm_proxy.provider_default,
        model=model or settings.llm_proxy.model,
        prompt_length=len(prompt),
    )

    full_response = []

    async for chunk in llm_server.generate(
        prompt=prompt,
        provider=provider,
        model=model,
        stream=stream,
        temperature=temperature,
        max_tokens=max_tokens,
    ):
        # Extract content based on provider format
        if "message" in chunk:
            content = chunk["message"].get("content", "")
        elif "choices" in chunk:
            content = chunk["choices"][0].get("delta", {}).get("content", "")
        else:
            content = str(chunk)

        full_response.append(content)

    return "".join(full_response)


@llm_proxy_mcp.tool()
async def llm_list_models(provider: str | None = None) -> list[dict[str, Any]]:
    """
    List available models from the specified LLM provider.

    Args:
        provider: LLM provider (ollama or llamacpp)

    Returns:
        List of available models with their details
    """
    logger.info(
        "llm_list_models_request",
        provider=provider or settings.llm_proxy.provider_default,
    )

    models = await llm_server.list_models(provider)
    return models


@llm_proxy_mcp.tool()
async def llm_switch_model(model: str, provider: str | None = None) -> dict[str, Any]:
    """
    Switch to a different model on the specified provider.

    Args:
        model: Name of the model to switch to
        provider: LLM provider (ollama or llamacpp)

    Returns:
        Status of the model switch operation
    """
    result = await llm_server.switch_model(model, provider)
    return result


@llm_proxy_mcp.tool()
async def llm_get_metrics() -> dict[str, Any]:
    """
    Get performance metrics for the LLM proxy.

    Returns:
        Metrics including requests, errors, latency, and token counts
    """
    return llm_server.get_metrics()


@llm_proxy_mcp.resource(uri="llm://status")
async def llm_status() -> str:
    """
    Get current LLM proxy status and configuration.

    Returns:
        JSON string with status information
    """
    status = {
        "enabled": settings.llm_proxy.enabled,
        "default_provider": settings.llm_proxy.provider_default,
        "default_model": settings.llm_proxy.model,
        "configured_providers": list(llm_server.clients.keys()),
        "metrics": llm_server.get_metrics(),
    }
    return json.dumps(status, indent=2)
