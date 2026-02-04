"""
Unit tests for LlamaCppClient.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx

from pulsenode.mcp.clients.llamacpp_client import (
    LlamaCppClient,
    ChatMessage,
    LlamaCppRequest,
)


@pytest.fixture
def llamacpp_client():
    """Create a LlamaCppClient instance for testing."""
    return LlamaCppClient(
        endpoint="http://localhost:8080",
        model="llama2",
        api_key="test-key",
        read_timeout=30.0,
        connect_timeout=10.0,
        max_retries=3,
        retry_backoff_factor=2.0,
    )


@pytest.mark.unit
class TestLlamaCppClient:
    """Test cases for LlamaCppClient."""

    def test_init(self):
        """Test LlamaCppClient initialization."""
        client = LlamaCppClient(
            endpoint="http://test.com:8080",
            model="test-model",
            api_key="test-key",
            read_timeout=45.0,
            connect_timeout=15.0,
            max_retries=5,
            retry_backoff_factor=3.0,
        )

        assert client.base_url == "http://test.com:8080"
        assert client.model == "test-model"
        assert client.api_key == "test-key"
        assert client.read_timeout == 45.0
        assert client.connect_timeout == 15.0
        assert client.max_retries == 5
        assert client.retry_backoff_factor == 3.0
        assert "requests" in client.metrics
        assert "errors" in client.metrics
        assert "timeouts" in client.metrics

    def test_get_headers_without_api_key(self):
        """Test header generation without API key."""
        client = LlamaCppClient("http://localhost:8080", "llama2")
        headers = client._get_headers()

        assert headers["Content-Type"] == "application/json"
        assert "Authorization" not in headers

    def test_get_headers_with_api_key(self):
        """Test header generation with API key."""
        client = LlamaCppClient("http://localhost:8080", "llama2", api_key="test-key")
        headers = client._get_headers()

        assert headers["Content-Type"] == "application/json"
        assert headers["Authorization"] == "Bearer test-key"

    @pytest.mark.asyncio
    async def test_chat_success(self, llamacpp_client):
        """Test successful chat request."""
        mock_response = MagicMock()

        # Create an async iterator mock
        async def mock_aiter_lines():
            lines = [
                'data: {"choices": [{"delta": {"content": "Hello"}}]}',
                'data: {"choices": [{"delta": {"content": " world"}}]}',
                "data: [DONE]",
            ]
            for line in lines:
                yield line

        mock_response.aiter_lines = mock_aiter_lines

        mock_stream_context = AsyncMock()
        mock_stream_context.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream_context.__aexit__ = AsyncMock(return_value=None)

        with patch.object(
            llamacpp_client.session, "stream", return_value=mock_stream_context
        ):
            chunks = []
            async for chunk in llamacpp_client.chat(
                [{"role": "user", "content": "Hello"}]
            ):
                chunks.append(chunk)

            assert len(chunks) == 2
            assert llamacpp_client.metrics["requests"] == 1
            assert llamacpp_client.metrics["errors"] == 0

    @pytest.mark.asyncio
    async def test_chat_read_timeout_retry(self, llamacpp_client):
        """Test read timeout with retry logic."""
        mock_stream_context = AsyncMock()
        mock_stream_context.__aenter__ = AsyncMock(
            side_effect=httpx.ReadTimeout("Read timeout")
        )
        mock_stream_context.__aexit__ = AsyncMock(return_value=None)

        with patch.object(
            llamacpp_client.session, "stream", return_value=mock_stream_context
        ):
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                with pytest.raises(Exception, match="llama.cpp read timeout after"):
                    async for _ in llamacpp_client.chat(
                        [{"role": "user", "content": "Hello"}]
                    ):
                        pass

                # Verify retry attempts
                assert (
                    llamacpp_client.session.stream.call_count == 4
                )  # 1 initial + 3 retries
                assert llamacpp_client.metrics["timeouts"] > 0
                assert llamacpp_client.metrics["errors"] == 1
                # Verify exponential backoff
                assert mock_sleep.call_count == 3

    @pytest.mark.asyncio
    async def test_list_models(self, llamacpp_client):
        """Test model listing (llama.cpp typically loads one model)."""
        models = await llamacpp_client.list_models()

        assert len(models) == 1
        assert models[0]["name"] == "llama2"
        assert models[0]["provider"] == "llamacpp"

    @pytest.mark.asyncio
    async def test_switch_model(self, llamacpp_client):
        """Test model switching."""
        result = await llamacpp_client.switch_model("new-model")

        assert llamacpp_client.model == "new-model"
        assert result["model"] == "new-model"
        assert result["status"] == "switched"
        assert (
            "requires restart" in result["note"].lower()
            or "restart" in result["note"].lower()
        )

    @pytest.mark.asyncio
    async def test_close(self, llamacpp_client):
        """Test client cleanup."""
        with patch.object(
            llamacpp_client.session, "aclose", new_callable=AsyncMock
        ) as mock_close:
            await llamacpp_client.close()
            mock_close.assert_called_once()


class TestChatMessage:
    """Test cases for ChatMessage model."""

    def test_chat_message_creation(self):
        """Test ChatMessage model validation."""
        message = ChatMessage(role="user", content="Hello")

        assert message.role == "user"
        assert message.content == "Hello"


class TestLlamaCppRequest:
    """Test cases for LlamaCppRequest model."""

    def test_llamacpp_request_creation(self):
        """Test LlamaCppRequest model validation."""
        messages = [ChatMessage(role="user", content="Hello")]
        request = LlamaCppRequest(
            model="llama2",
            messages=messages,
            stream=True,
            temperature=0.7,
            max_tokens=100,
        )

        assert request.model == "llama2"
        assert len(request.messages) == 1
        assert request.messages[0].role == "user"
        assert request.messages[0].content == "Hello"
        assert request.stream is True
        assert request.temperature == 0.7
        assert request.max_tokens == 100
