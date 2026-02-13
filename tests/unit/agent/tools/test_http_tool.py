#!/usr/bin/env python3
"""Tests for HTTP tool."""

import pytest

from pulsenode.agent.tools.http import HttpTool
from pulsenode.agent.agent_config import HttpConfig


@pytest.fixture
def http_config():
    return HttpConfig(
        enabled=True,
        allowed_hosts=[],
        blocked_hosts=[],
        require_confirmation=False,
        default_timeout=30,
    )


@pytest.fixture
def http_tool(http_config):
    return HttpTool(http_config)


@pytest.mark.asyncio
async def test_http_tool__is_host_allowed__empty_allowlist(http_tool):
    """When allowed_hosts is empty, any host should be allowed."""
    allowed, error = http_tool._is_host_allowed("https://example.com")
    assert allowed is True
    assert error == ""


@pytest.mark.asyncio
async def test_http_tool__is_host_allowed__whitelist_match(http_tool):
    """When host matches whitelist, should be allowed."""
    http_tool.config.allowed_hosts = ["example.com", "api.github.com"]
    allowed, error = http_tool._is_host_allowed("https://api.github.com/users")
    assert allowed is True


@pytest.mark.asyncio
async def test_http_tool__is_host_allowed__whitelist_no_match(http_tool):
    """When host doesn't match whitelist, should be blocked."""
    http_tool.config.allowed_hosts = ["example.com"]
    allowed, error = http_tool._is_host_allowed("https://evil.com")
    assert allowed is False
    assert "not in allowed list" in error


@pytest.mark.asyncio
async def test_http_tool__is_host_allowed__blocklist_match(http_tool):
    """When host matches blocklist, should be blocked."""
    http_tool.config.blocked_hosts = ["evil.com", "malicious.org"]
    allowed, error = http_tool._is_host_allowed("https://evil.com/attack")
    assert allowed is False
    assert "blocked" in error.lower()


@pytest.mark.asyncio
async def test_http_tool__is_host_allowed__blocklist_takes_precedence(http_tool):
    """Blocklist should take precedence over allowlist."""
    http_tool.config.allowed_hosts = ["example.com", "evil.com"]
    http_tool.config.blocked_hosts = ["evil.com"]
    allowed, error = http_tool._is_host_allowed("https://evil.com")
    assert allowed is False


@pytest.mark.asyncio
async def test_http_tool__parse_url__valid():
    """Parse URL should extract scheme and host."""
    config = HttpConfig()
    tool = HttpTool(config)
    scheme, host = tool._parse_url("https://api.example.com/v1/users")
    assert scheme == "https"
    assert host == "api.example.com"


@pytest.mark.asyncio
async def test_http_tool__parse_url__invalid():
    """Parse URL should return empty strings for invalid URL."""
    config = HttpConfig()
    tool = HttpTool(config)
    scheme, host = tool._parse_url("not-a-url")
    assert scheme == ""
    assert host == ""


@pytest.mark.asyncio
async def test_http_tool__get__blocked_host(http_tool):
    """GET request to blocked host should fail."""
    http_tool.config.blocked_hosts = ["evil.com"]
    result = await http_tool.get("https://evil.com")
    assert result["success"] is False
    assert "blocked" in result["error"].lower()


@pytest.mark.asyncio
async def test_http_tool__metrics__initial(http_tool):
    """Initial metrics should be zero."""
    metrics = http_tool.get_metrics()
    assert metrics["requests"] == 0
    assert metrics["errors"] == 0
    assert metrics["total_duration"] == 0.0


@pytest.mark.asyncio
async def test_http_tool__close(http_tool):
    """Close should cleanup the client."""
    await http_tool.close()
    assert http_tool._client is None


@pytest.mark.asyncio
async def test_http_tool__get_client__creates_client(http_tool):
    """Getting client should create it if not exists."""
    http_tool._client = None
    client = await http_tool._get_client()
    assert client is not None
    assert http_tool._client is not None
