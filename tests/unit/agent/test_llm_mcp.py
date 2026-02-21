"""
Unit tests for LlmMcp class.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from pulsenode.agent.llm_mcp import LlmMcp, TriageResponse


@pytest.fixture
def llm_mcp():
    """Create a LlmMcp instance for testing."""
    mcp = LlmMcp(
        mcp_url="http://localhost:8000/mcp", auth_token="test-token", max_tokens=100
    )
    mcp.session_id = "test-session-id"
    return mcp


@pytest.mark.unit
class TestLlmMcp:
    """Test cases for LlmMcp class."""

    def test_init(self):
        """Test LlmMcp initialization."""
        mcp = LlmMcp(
            mcp_url="http://test.com/mcp", auth_token="test-auth", max_tokens=50
        )

        assert mcp.mcp_url == "http://test.com/mcp"
        assert mcp.auth_token == "test-auth"
        assert mcp.max_tokens == 50

    @pytest.mark.asyncio
    async def test_generate_response_success(self, llm_mcp):
        """Test successful response generation."""
        mock_response = MagicMock()
        mock_response.text = (
            'data: {"result": {"content": [{"type": "text", "text": "Test response"}]}}'
        )

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.post.return_value = mock_response

            result = await llm_mcp.generate_response("Hello, test!")

            assert result.content == "Test response"
            mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_triage_response_needed(self, llm_mcp):
        """Test triage response when action is needed."""
        mock_response = MagicMock()
        mock_response.text = 'data: {"result": {"content": [{"type": "text", "text": "ACTION_NEEDED: This requires immediate attention"}]}}'

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.post.return_value = mock_response

            result = await llm_mcp.generate_triage_response("Urgent message")

            assert result.needed is True
            assert "immediate attention" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_generate_triage_response_not_needed(self, llm_mcp):
        """Test triage response when no action is needed."""
        mock_response = MagicMock()
        mock_response.text = 'data: {"result": {"content": [{"type": "text", "text": "No triage required for this notification"}]}}'

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.post.return_value = mock_response

            result = await llm_mcp.generate_triage_response("Regular message")

            assert result.needed is False
            assert "notification" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_generate_triage_response_json_format(self, llm_mcp):
        """Test triage response with proper JSON format from LLM."""
        mock_response = MagicMock()
        mock_response.text = 'data: {"result": {"content": [{"type": "text", "text": "{\\"needed\\": true, \\"reason\\": \\"This is urgent\\"}"}]}}'

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.post.return_value = mock_response

            result = await llm_mcp.generate_triage_response("Urgent message")

            assert result.needed is True
            assert result.reason == "This is urgent"

    @pytest.mark.asyncio
    async def test_chat_with_llm_default_provider(self, llm_mcp):
        """Test chat with LLM using default provider."""
        mock_response = MagicMock()
        mock_response.text = (
            'data: {"result": {"content": [{"type": "text", "text": "Chat response"}]}}'
        )

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.post.return_value = mock_response

            result = await llm_mcp.chat_with_llm([{"role": "user", "content": "Hello"}])

            assert result == "Chat response"
            mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_chat_with_llm_specific_provider(self, llm_mcp):
        """Test chat with LLM using specific provider."""
        mock_response = MagicMock()
        mock_response.text = 'data: {"result": {"content": [{"type": "text", "text": "Provider-specific response"}]}}'

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.post.return_value = mock_response

            result = await llm_mcp.chat_with_llm(
                [{"role": "user", "content": "Hello"}], provider="ollama"
            )

            assert result == "Provider-specific response"

    def test_triage_response_model(self):
        """Test TriageResponse model validation."""
        response = TriageResponse(needed=True, reason="Test reason")

        assert response.needed is True
        assert response.reason == "Test reason"

        # Test with different values
        response2 = TriageResponse(needed=False, reason="No action needed")
        assert response2.needed is False
        assert response2.reason == "No action needed"

    @pytest.mark.asyncio
    async def test_mcp_request_error_handling(self, llm_mcp):
        """Test error handling in MCP requests."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.post.side_effect = Exception("Network error")

            result = await llm_mcp.generate_response("Test message")

            assert "Network error" in result.content

    @pytest.mark.asyncio
    async def test_empty_response_handling(self, llm_mcp):
        """Test handling of empty or malformed responses."""
        mock_response = MagicMock()
        mock_response.text = 'data: {"result": {"content": []}}'

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.post.return_value = mock_response

            result = await llm_mcp.generate_response("Test")

            assert result.content == "No response generated"
