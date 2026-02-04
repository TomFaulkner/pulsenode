"""
Unit tests for LLM proxy server.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastmcp import Context

from pulsenode.mcp.servers.llm_proxy import (
    LLMProxyServer,
    ChatMessage,
    LLMRequest,
    LLMResponse,
)
from pulsenode.mcp.clients.ollama_client import OllamaClient
from pulsenode.mcp.clients.llamacpp_client import LlamaCppClient


@pytest.fixture
def mock_context():
    """Create a mock MCP context."""
    context = MagicMock(spec=Context)
    context.request_id = "test-request-id"
    return context


@pytest.fixture
def mock_ollama_client():
    """Create a mock OllamaClient."""
    client = MagicMock(spec=OllamaClient)
    client.chat = AsyncMock()
    client.generate = AsyncMock()
    client.list_models = AsyncMock()
    client.get_metrics = MagicMock(return_value={"requests": 10, "errors": 1})
    return client


@pytest.fixture
def mock_llamacpp_client():
    """Create a mock LlamaCppClient."""
    client = MagicMock(spec=LlamaCppClient)
    client.chat = AsyncMock()
    client.generate = AsyncMock()
    client.list_models = AsyncMock()
    client.get_metrics = MagicMock(return_value={"requests": 5, "errors": 0})
    return client


class TestLLMProxyServer:
    """Test cases for LLMProxyServer."""

    def test_init_with_no_config(self):
        """Test LLMProxyServer initialization without config."""
        server = LLMProxyServer()

        assert len(server.clients) == 0
        assert server.metrics["requests"] == 0
        assert server.metrics["errors"] == 0
        assert "total_latency" in server.metrics
        assert "total_tokens" in server.metrics

    def test_init_with_config(self):
        """Test LLMProxyServer initialization with config."""
        config = {
            "ollama": {
                "endpoint": "http://localhost:11434",
                "model": "llama2",
                "api_key": "test-key",
            },
            "llamacpp": {"endpoint": "http://localhost:8080", "model": "codellama"},
        }
        server = LLMProxyServer()

        assert len(server.clients) == 2
        assert "ollama" in server.clients
        assert "llamacpp" in server.clients

    @pytest.mark.asyncio
    async def test_chat_with_default_provider(self, mock_context, mock_ollama_client):
        """Test chat with default provider."""
        server = LLMProxyServer()
        server.clients["ollama"] = mock_ollama_client

        # Mock streaming response
        async def mock_stream():
            yield {"message": {"content": "Hello"}}
            yield {"done": True}

        mock_ollama_client.chat.return_value = mock_stream()

        # The chat method returns an async generator, so we need to consume it
        chunks = []
        async for chunk in server.chat(messages=[{"role": "user", "content": "Hello"}]):
            chunks.append(chunk)

        # Verify the generator was consumed and client was called
        assert len(chunks) > 0
        mock_ollama_client.chat.assert_called_once()

    @pytest.mark.asyncio
    async def test_chat_with_specific_provider(
        self, mock_context, mock_llamacpp_client
    ):
        """Test chat with specific provider."""
        server = LLMProxyServer()
        server.clients["llamacpp"] = mock_llamacpp_client

        # Mock streaming response
        async def mock_stream():
            yield {"choices": [{"delta": {"content": "Hi there"}}]}
            yield {"done": True}

        mock_llamacpp_client.chat.return_value = mock_stream()

        # The chat method returns an async generator, so we need to consume it
        chunks = []
        async for chunk in server.chat(
            messages=[{"role": "user", "content": "Hello"}],
            provider="llamacpp",
        ):
            chunks.append(chunk)

        # Verify the generator was consumed and client was called
        assert len(chunks) > 0
        mock_llamacpp_client.chat.assert_called_once()

    def test_llm_response_optional_fields(self):
        """Test LLMResponse with optional fields."""
        response = LLMResponse(content="Hello", model="llama2", provider="ollama")

        assert response.content == "Hello"
        assert response.tokens_used is None
        assert response.duration_ms is None
