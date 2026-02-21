"""
Unit tests for agent main functionality.
"""

import pytest
from unittest.mock import MagicMock

from pulsenode.config.settings import Settings, LLMProxyConfig


@pytest.mark.unit
class TestAgentMain:
    """Test cases for agent main functionality."""

    def test_settings_validation(self):
        """Test settings validation."""
        settings = Settings(
            heartbeat_interval_seconds=30,
            llm_proxy=LLMProxyConfig(
                enabled=True,
                provider_default="ollama",
                endpoint="http://localhost:11434",
                model="llama2",
                api_key=None,
                temperature=0.7,
                max_tokens=100,
                stream=True,
            ),
        )

        assert settings.heartbeat_interval_seconds == 30
        assert settings.llm_proxy.enabled is True
        assert settings.llm_proxy.provider_default == "ollama"
        assert settings.llm_proxy.model == "llama2"
        assert settings.llm_proxy.temperature == 0.7
        assert settings.llm_proxy.max_tokens == 100

    def test_llm_proxy_config_validation(self):
        """Test LLMProxyConfig validation."""
        config = LLMProxyConfig(
            enabled=True,
            provider_default="ollama",
            endpoint="http://localhost:11434",
            model="llama2",
            api_key="test-key",
            temperature=0.7,
            max_tokens=100,
            stream=True,
        )

        assert config.enabled is True
        assert config.provider_default == "ollama"
        assert config.endpoint == "http://localhost:11434"
        assert config.model == "llama2"
        assert config.api_key == "test-key"
        assert config.temperature == 0.7
        assert config.max_tokens == 100
        assert config.stream is True

    def test_agent_constructor_exists(self):
        """Test Agent class exists and has expected constructor."""
        from pulsenode.agent.main import Agent

        # Verify Agent class exists
        assert Agent is not None

        # Verify it has expected constructor parameters
        import inspect

        sig = inspect.signature(Agent.__init__)
        params = list(sig.parameters.keys())

        # Should have at least these key parameters
        required_params = ["self", "triage_llm", "capable_llm", "context", "settings"]
        for param in required_params:
            assert param in params

    def test_heartbeat_logging(self, monkeypatch):
        """Test heartbeat logging functionality."""
        mock_logger = MagicMock()
        monkeypatch.setattr("pulsenode.agent.main.logger", mock_logger)

        from pulsenode.agent.main import Agent

        assert hasattr(Agent, "heartbeat")
        assert callable(getattr(Agent, "heartbeat"))
