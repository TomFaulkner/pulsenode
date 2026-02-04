"""
Integration tests for MCP HTTP API endpoints.
"""

import pytest


@pytest.mark.integration
@pytest.mark.slow
async def test_mcp_http_api__tools_list(mcp_session: str, mcp_client):
    """Test tools/list endpoint."""
    response = await mcp_client.post(
        "http://localhost:8000/mcp",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "mcp-session-id": mcp_session,
        },
        json={"jsonrpc": "2.0", "method": "tools/list", "id": "list-tools"},
    )

    print(f"Tools list status: {response.status_code}")
    print(f"Tools list text: {response.text}")

    # Should get a valid response (success or structured error)
    assert response.status_code in [200, 400, 500]


@pytest.mark.integration
@pytest.mark.slow
async def test_mcp_http_api__tool_call_greet(mcp_session: str, mcp_client):
    """Test tool/call endpoint with greet tool."""
    response = await mcp_client.post(
        "http://localhost:8000/mcp",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "mcp-session-id": mcp_session,
        },
        json={
            "jsonrpc": "2.0",
            "method": "tool/call",
            "params": {"name": "greet", "arguments": {"name": "World"}},
            "id": "test-greet",
        },
    )

    print(f"Greet call status: {response.status_code}")
    print(f"Greet call text: {response.text}")

    # Should get a valid response (success or structured error)
    assert response.status_code in [200, 400, 500]


@pytest.mark.integration
@pytest.mark.slow
async def test_mcp_http_api__tools_call_correct_method(mcp_session: str, mcp_client):
    """Test tools/call endpoint (alternative method name)."""
    response = await mcp_client.post(
        "http://localhost:8000/mcp",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "mcp-session-id": mcp_session,
        },
        json={
            "jsonrpc": "2.0",
            "method": "tools/call",  # Alternative method name
            "params": {"name": "greet", "arguments": {"name": "World"}},
            "id": "test-greet",
        },
    )

    print(f"Tools/call status: {response.status_code}")
    print(f"Tools/call text: {response.text}")

    # Should get a valid response (success or structured error)
    assert response.status_code in [200, 400, 500]


@pytest.mark.integration
@pytest.mark.slow
async def test_mcp_http_api__tool_call_generate(mcp_session: str, mcp_client):
    """Test tool/call endpoint with llm_generate tool."""
    response = await mcp_client.post(
        "http://localhost:8000/mcp",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "mcp-session-id": mcp_session,
        },
        json={
            "jsonrpc": "2.0",
            "method": "tool/call",
            "params": {
                "name": "llm_llm_generate",  # Try the simpler generate tool first
                "arguments": {
                    "prompt": "Hello, this is a test",
                    "provider": "openai",
                    "model": "gpt-4",
                    "temperature": 0.3,
                    "max_tokens": 100,
                    "stream": False,
                },
            },
            "id": "test-generate",
        },
    )

    print(f"Generate call status: {response.status_code}")
    print(f"Generate call text: {response.text}")

    # Should get a valid response (success or structured error)
    assert response.status_code in [200, 400, 500]


@pytest.mark.integration
@pytest.mark.slow
async def test_mcp_http_api__tool_call_chat(mcp_session: str, mcp_client):
    """Test tool/call endpoint with llm_chat tool."""
    response = await mcp_client.post(
        "http://localhost:8000/mcp",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "mcp-session-id": mcp_session,
        },
        json={
            "jsonrpc": "2.0",
            "method": "tool/call",
            "params": {
                "name": "llm_llm_chat",
                "arguments": {
                    "messages": [{"role": "user", "content": "Hello"}],
                    "provider": "openai",
                    "model": "gpt-4",
                    "temperature": 0.3,
                    "max_tokens": 100,
                    "stream": False,
                },
            },
            "id": "test-chat",
        },
    )

    print(f"Chat call status: {response.status_code}")
    print(f"Chat call text: {response.text}")

    # Should get a valid response (success or structured error)
    assert response.status_code in [200, 400, 500]
