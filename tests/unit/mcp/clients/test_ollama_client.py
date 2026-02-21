"""
Unit tests for OllamaClient.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx

from pulsenode.mcp.clients.ollama_client import OllamaClient, ChatMessage, ChatRequest


@pytest.fixture
def ollama_client():
    """Create an OllamaClient instance for testing."""
    return OllamaClient(
        endpoint="http://localhost:11434",
        model="llama2",
        api_key="test-key",
        read_timeout=30.0,
        connect_timeout=10.0,
        max_retries=3,
        retry_backoff_factor=2.0,
    )


@pytest.mark.unit
class TestOllamaClient:
    """Test cases for OllamaClient."""

    def test_init(self):
        """Test OllamaClient initialization."""
        client = OllamaClient(
            endpoint="http://test.com:11434",
            model="test-model",
            api_key="test-key",
            read_timeout=45.0,
            connect_timeout=15.0,
            max_retries=5,
            retry_backoff_factor=3.0,
        )

        assert client.base_url == "http://test.com:11434/api"
        assert client.model == "test-model"
        assert client.api_key == "test-key"
        assert client.read_timeout == 45.0
        assert client.connect_timeout == 15.0
        assert client.max_retries == 5
        assert client.retry_backoff_factor == 3.0
        assert "requests" in client.metrics
        assert "errors" in client.metrics
        assert "timeouts" in client.metrics

    def test_init_default_values(self):
        """Test OllamaClient initialization with default values."""
        client = OllamaClient("http://localhost:11434", "llama2")

        assert client.read_timeout == 30.0
        assert client.connect_timeout == 10.0
        assert client.max_retries == 3
        assert client.retry_backoff_factor == 2.0
        assert client.api_key is None

    def test_get_headers_without_api_key(self):
        """Test header generation without API key."""
        client = OllamaClient("http://localhost:11434", "llama2")
        headers = client._get_headers()

        assert headers["Content-Type"] == "application/json"
        assert "Authorization" not in headers

    def test_get_headers_with_api_key(self):
        """Test header generation with API key."""
        client = OllamaClient("http://localhost:11434", "llama2", api_key="test-key")
        headers = client._get_headers()

        assert headers["Content-Type"] == "application/json"
        assert headers["Authorization"] == "Bearer test-key"

    def test_get_metrics(self):
        """Test metrics retrieval."""
        client = OllamaClient("http://localhost:11434", "llama2")
        client.metrics["requests"] = 10
        client.metrics["errors"] = 2

        metrics = client.get_metrics()

        assert metrics["requests"] == 10
        assert metrics["errors"] == 2
        # Ensure it returns a copy, not reference
        metrics["requests"] = 20
        assert client.metrics["requests"] == 10

    @pytest.mark.asyncio
    async def test_chat_success(self, ollama_client):
        """Test successful chat request."""
        mock_response = MagicMock()

        # Create an async iterator mock
        async def mock_aiter_lines():
            lines = [
                '{"message": {"content": "Hello"}}',
                '{"message": {"content": " world"}}',
                '{"done": true}',
            ]
            for line in lines:
                yield line

        mock_response.aiter_lines = mock_aiter_lines

        mock_stream_context = AsyncMock()
        mock_stream_context.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream_context.__aexit__ = AsyncMock(return_value=None)

        with patch.object(
            ollama_client.session, "stream", return_value=mock_stream_context
        ):
            chunks = []
            async for chunk in ollama_client.chat(
                [{"role": "user", "content": "Hello"}]
            ):
                chunks.append(chunk)

            assert len(chunks) == 3
            assert ollama_client.metrics["requests"] == 1
            assert ollama_client.metrics["errors"] == 0

    @pytest.mark.asyncio
    async def test_chat_read_timeout_retry(self, ollama_client):
        """Test read timeout with retry logic."""
        mock_stream_context = AsyncMock()
        mock_stream_context.__aenter__ = AsyncMock(
            side_effect=httpx.ReadTimeout("Read timeout")
        )
        mock_stream_context.__aexit__ = AsyncMock(return_value=None)

        with patch.object(
            ollama_client.session, "stream", return_value=mock_stream_context
        ):
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                with pytest.raises(Exception, match="Ollama read timeout after"):
                    async for _ in ollama_client.chat(
                        [{"role": "user", "content": "Hello"}]
                    ):
                        pass

                # Verify retry attempts
                assert (
                    ollama_client.session.stream.call_count == 4
                )  # 1 initial + 3 retries
                assert ollama_client.metrics["timeouts"] > 0
                assert ollama_client.metrics["errors"] == 1
                # Verify exponential backoff
                assert mock_sleep.call_count == 3

    @pytest.mark.asyncio
    async def test_chat_connect_timeout(self, ollama_client):
        """Test connect timeout handling."""
        mock_stream_context = AsyncMock()
        mock_stream_context.__aenter__ = AsyncMock(
            side_effect=httpx.ConnectTimeout("Connect timeout")
        )
        mock_stream_context.__aexit__ = AsyncMock(return_value=None)

        with patch.object(
            ollama_client.session, "stream", return_value=mock_stream_context
        ):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                with pytest.raises(Exception, match="Ollama connect timeout after"):
                    async for _ in ollama_client.chat(
                        [{"role": "user", "content": "Hello"}]
                    ):
                        pass

                assert ollama_client.metrics["timeouts"] > 0
                assert ollama_client.metrics["errors"] == 1

    @pytest.mark.asyncio
    async def test_chat_custom_timeout(self, ollama_client):
        """Test chat with custom per-request timeout."""
        mock_response = MagicMock()

        # Create an async iterator mock
        async def mock_aiter_lines():
            return
            yield  # Empty generator

        mock_response.aiter_lines = mock_aiter_lines
        mock_stream_context = AsyncMock()
        mock_stream_context.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream_context.__aexit__ = AsyncMock(return_value=None)

        with patch.object(ollama_client.session, "stream") as mock_stream:
            mock_stream.return_value = mock_stream_context

            async for _ in ollama_client.chat(
                [{"role": "user", "content": "Hello"}], read_timeout=60.0
            ):
                pass

            # Verify custom timeout was used
            call_kwargs = mock_stream.call_args[1]
            assert call_kwargs["timeout"].read == 60.0

    @pytest.mark.asyncio
    async def test_list_models_success(self, ollama_client):
        """Test successful model listing."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "models": [{"name": "llama2"}, {"name": "codellama"}]
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(ollama_client.session, "get", return_value=mock_response):
            models = await ollama_client.list_models()

            assert len(models) == 2
            assert models[0]["name"] == "llama2"
            assert models[1]["name"] == "codellama"

    @pytest.mark.asyncio
    async def test_list_models_timeout(self, ollama_client):
        """Test timeout in list_models."""
        with patch.object(
            ollama_client.session, "get", side_effect=httpx.ReadTimeout("Timeout")
        ):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                with pytest.raises(
                    Exception, match="Failed to list models due to read timeout"
                ):
                    await ollama_client.list_models()

                assert ollama_client.metrics["timeouts"] > 0

    @pytest.mark.asyncio
    async def test_switch_model(self, ollama_client):
        """Test model switching."""
        result = await ollama_client.switch_model("new-model")

        assert ollama_client.model == "new-model"
        assert result["model"] == "new-model"
        assert result["status"] == "switched"

    @pytest.mark.asyncio
    async def test_close(self, ollama_client):
        """Test client cleanup."""
        with patch.object(
            ollama_client.session, "aclose", new_callable=AsyncMock
        ) as mock_close:
            await ollama_client.close()
            mock_close.assert_called_once()


class TestChatMessage:
    """Test cases for ChatMessage model."""

    def test_chat_message_creation(self):
        """Test ChatMessage model validation."""
        message = ChatMessage(role="user", content="Hello")

        assert message.role == "user"
        assert message.content == "Hello"


class TestChatRequest:
    """Test cases for ChatRequest model."""

    def test_chat_request_creation(self):
        """Test ChatRequest model validation."""
        messages = [ChatMessage(role="user", content="Hello")]
        request = ChatRequest(
            model="llama2", messages=messages, stream=True, options={"temperature": 0.7}
        )

        assert request.model == "llama2"
        assert len(request.messages) == 1
        assert request.messages[0].role == "user"
        assert request.messages[0].content == "Hello"
        assert request.stream is True
        assert request.options["temperature"] == 0.7
