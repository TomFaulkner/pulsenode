"""
Integration tests for LlmMcp agent functionality.
"""

import pytest
import sys
import os

# Add src to path for test imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../..", "src"))

from pulsenode.agent.llm_mcp import LlmMcp


@pytest.fixture
def llm_mcp_instance() -> LlmMcp:
    """Create LlmMcp instance for integration testing."""
    return LlmMcp(
        mcp_url="http://localhost:8000/mcp", auth_token="dummy", max_tokens=100
    )


@pytest.mark.integration
@pytest.mark.slow
async def test_llm_mcp__generate_response(llm_mcp_instance: LlmMcp):
    """Test LlmMcp generate_response method."""
    result = await llm_mcp_instance.generate_response("Hello, test message")
    assert result is not None
    print(f"Generate response result: {result}")


@pytest.mark.integration
@pytest.mark.slow
async def test_llm_mcp__generate_triage_response(llm_mcp_instance: LlmMcp):
    """Test LlmMcp generate_triage_response method."""
    triage = await llm_mcp_instance.generate_triage_response("This needs action now")
    assert triage is not None
    assert hasattr(triage, "needed")
    assert hasattr(triage, "reason")
    print(f"Triage result: needed={triage.needed}, reason={triage.reason}")


@pytest.mark.integration
@pytest.mark.slow
async def test_llm_mcp__chat_with_llm(llm_mcp_instance: LlmMcp):
    """Test LlmMcp chat_with_llm method."""
    messages = [{"role": "user", "content": "Hello again"}]
    chat_result = await llm_mcp_instance.chat_with_llm(messages)
    assert chat_result is not None
    print(f"Chat result: {chat_result}")


@pytest.mark.integration
@pytest.mark.slow
async def test_llm_mcp__list_available_models(llm_mcp_instance: LlmMcp):
    """Test LlmMcp list_available_models method."""
    models = await llm_mcp_instance.list_available_models()
    assert models is not None
    print(f"Available models: {models}")


@pytest.mark.integration
@pytest.mark.slow
async def test_llm_mcp__switch_llm_model(llm_mcp_instance: LlmMcp):
    """Test LlmMcp switch_llm_model method."""
    switch_result = await llm_mcp_instance.switch_llm_model("some-model")
    assert switch_result is not None
    print(f"Switch result: {switch_result}")
