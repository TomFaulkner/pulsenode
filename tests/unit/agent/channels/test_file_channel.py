#!/usr/bin/env python3
"""Tests for FileChannelMcp."""

import pytest
import tempfile
from pathlib import Path

from pulsenode.agent.channels.file_channel import FileChannelMcp


@pytest.fixture
def temp_file():
    """Create a temporary file for testing."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        temp_path = Path(f.name)
    yield temp_path
    # Cleanup
    if temp_path.exists():
        temp_path.unlink()


@pytest.fixture
def sample_content():
    """Sample file content for testing."""
    return """message 1
---
message 2
---
message 3
+++
batch 2 message 1
---
batch 2 message 2
"""


@pytest.mark.asyncio
async def test_file_channel_mcp__parse_file__empty(temp_file):
    """Empty file should return empty batches."""
    channel = FileChannelMcp(file_path=temp_file)
    batches = channel._parse_file()
    assert batches == []


@pytest.mark.asyncio
async def test_file_channel_mcp__parse_file__single_message(temp_file):
    """Single message without separators."""
    temp_file.write_text("hello world")
    channel = FileChannelMcp(file_path=temp_file)
    batches = channel._parse_file()
    assert batches == [["hello world"]]


@pytest.mark.asyncio
async def test_file_channel_mcp__parse_file__multiple_messages(
    temp_file, sample_content
):
    """Multiple messages with separators."""
    temp_file.write_text(sample_content)
    channel = FileChannelMcp(file_path=temp_file)
    batches = channel._parse_file()
    assert len(batches) == 2
    assert batches[0] == ["message 1", "message 2", "message 3"]
    assert batches[1] == ["batch 2 message 1", "batch 2 message 2"]


@pytest.mark.asyncio
async def test_file_channel_mcp__parse_file__separators_ignored(temp_file):
    """Separator lines should be ignored."""
    content = """msg1
---
msg2
+++
msg3
"""
    temp_file.write_text(content)
    channel = FileChannelMcp(file_path=temp_file)
    batches = channel._parse_file()
    assert batches == [["msg1", "msg2"], ["msg3"]]


@pytest.mark.asyncio
async def test_file_channel_mcp__parse_file__nonexistent(temp_file):
    """Nonexistent file should return empty batches."""
    temp_file.unlink()  # Remove the file
    channel = FileChannelMcp(file_path=temp_file)
    batches = channel._parse_file()
    assert batches == []


@pytest.mark.asyncio
async def test_file_channel_mcp__receive_messages__yields_messages(
    temp_file, sample_content
):
    """Should yield messages from the file."""
    temp_file.write_text(sample_content)
    channel = FileChannelMcp(file_path=temp_file, sleep_seconds=0)

    gen = channel.receive_messages()

    # First batch
    msg1 = await gen.__anext__()
    assert msg1 == "message 1"

    msg2 = await gen.__anext__()
    assert msg2 == "message 2"

    msg3 = await gen.__anext__()
    assert msg3 == "message 3"

    # Batch exhausted - should yield empty string
    empty = await gen.__anext__()
    assert empty == ""

    # Next batch
    msg4 = await gen.__anext__()
    assert msg4 == "batch 2 message 1"


@pytest.mark.asyncio
async def test_file_channel_mcp__receive_messages__exhausted_file(temp_file):
    """When file exhausted, should yield empty strings forever."""
    temp_file.write_text("single message")
    channel = FileChannelMcp(file_path=temp_file, sleep_seconds=0)

    gen = channel.receive_messages()

    # First message
    msg = await gen.__anext__()
    assert msg == "single message"

    # Batch exhausted
    empty1 = await gen.__anext__()
    assert empty1 == ""

    # File exhausted - should keep yielding empty
    empty2 = await gen.__anext__()
    assert empty2 == ""

    empty3 = await gen.__anext__()
    assert empty3 == ""


@pytest.mark.asyncio
async def test_file_channel_mcp__reload_if_needed__detects_modification(temp_file):
    """Should detect file modification."""
    temp_file.write_text("original")
    channel = FileChannelMcp(file_path=temp_file)

    # Initial load
    channel._reload_if_needed()
    assert channel._batches == [["original"]]

    # Modify file
    temp_file.write_text("modified")

    # Should detect modification
    reloaded = channel._reload_if_needed()
    assert reloaded is True
    assert channel._batches == [["modified"]]


@pytest.mark.asyncio
async def test_file_channel_mcp__reload_if_needed__no_change(temp_file):
    """Should not reload if file unchanged."""
    temp_file.write_text("content")
    channel = FileChannelMcp(file_path=temp_file)
    channel._reload_if_needed()

    # Try to reload again - should return False
    reloaded = channel._reload_if_needed()
    assert reloaded is False


@pytest.mark.asyncio
async def test_file_channel_mcp__defaults():
    """Test default values."""
    channel = FileChannelMcp(file_path=Path("/tmp/test.txt"))
    assert channel.name == "FileChannel"
    assert channel.type == "file"
    assert channel.identifier == ""
    assert channel.sleep_seconds == 3.0
