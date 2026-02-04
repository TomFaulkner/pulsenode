"""
Common fixtures for integration tests.
"""

import pytest
import httpx
from typing import AsyncGenerator


@pytest.fixture
async def mcp_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Create an HTTP client for MCP integration tests."""
    async with httpx.AsyncClient() as client:
        yield client


@pytest.fixture
async def mcp_session(mcp_client: httpx.AsyncClient) -> AsyncGenerator[str, None]:
    """Initialize an MCP session and return session ID."""
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

    # If server is not running, skip tests
    if init_response.status_code != 200:
        pytest.skip("MCP server not running on localhost:8000")

    session_id = init_response.headers.get("mcp-session-id")
    if not session_id:
        pytest.fail("No session ID returned from MCP server")

    yield session_id

    # No explicit cleanup needed - session will expire server-side
