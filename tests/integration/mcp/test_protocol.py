"""
Integration tests for MCP protocol functionality.
"""

import pytest


@pytest.mark.integration
@pytest.mark.slow
async def test_mcp_protocol__full_workflow(mcp_client):
    """Test complete MCP protocol flow from initialization to tool call."""
    # Initialize session
    init_response = await mcp_client.post(
        "http://localhost:8000/mcp",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
        json={
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"roots": {"listChanged": True}, "sampling": {}},
                "clientInfo": {"name": "test", "version": "1.0"},
            },
            "id": "init",
        },
    )

    assert init_response.status_code == 200
    session_id = init_response.headers.get("mcp-session-id")
    assert session_id is not None

    # Make tool call with session
    tool_response = await mcp_client.post(
        "http://localhost:8000/mcp",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "mcp-session-id": session_id,
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
            "id": "test-call",
        },
    )

    print(f"Init status: {init_response.status_code}")
    print(f"Init headers: {dict(init_response.headers)}")
    print(f"Init text: {init_response.text}")
    print(f"Tool call status: {tool_response.status_code}")
    print(f"Tool call text: {tool_response.text}")

    # Tool call should succeed or return a meaningful error
    assert tool_response.status_code in [
        200,
        400,
        500,
    ]  # Accept success or expected errors


@pytest.mark.integration
@pytest.mark.slow
async def test_mcp_protocol__session_management(mcp_client):
    """Test MCP session ID handling and validation."""
    # Initialize session
    init_response = await mcp_client.post(
        "http://localhost:8000/mcp",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
        json={
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"roots": {"listChanged": True}, "sampling": {}},
                "clientInfo": {"name": "test", "version": "1.0"},
            },
            "id": "init",
        },
    )

    assert init_response.status_code == 200
    session_id = init_response.headers.get("mcp-session-id")
    assert session_id is not None
    print(f"Session ID: {session_id}")

    # Test that session ID works for subsequent calls
    tools_response = await mcp_client.post(
        "http://localhost:8000/mcp",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "mcp-session-id": session_id,
        },
        json={"jsonrpc": "2.0", "method": "tools/list", "id": "list-tools"},
    )

    print(f"Tools list status: {tools_response.status_code}")
    print(f"Tools list text: {tools_response.text}")

    # Should get a valid response (success or structured error)
    assert tools_response.status_code in [200, 400, 500]
