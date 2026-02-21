#!/usr/bin/env python3

import asyncio
import sys
import os
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from pulsenode.agent.loader import AgentLoader
from pulsenode.agent.agent_config import AgentConfigManager, AgentConfig, LlmConfig
from pulsenode.config.settings import create_default_settings


async def test_loader_initialization():
    """Test AgentLoader initialization."""
    print("Testing AgentLoader initialization...")

    with tempfile.TemporaryDirectory() as temp_dir:
        base_dir = Path(temp_dir)
        settings = create_default_settings()
        loader = AgentLoader(base_dir, settings)

        assert loader.config_dir == base_dir
        assert loader.settings == settings
        assert isinstance(loader.config_manager, AgentConfigManager)

        print("✓ AgentLoader initialization works correctly")


async def test_load_agent_list_empty():
    """Test loading agent list when agents.yaml doesn't exist."""
    print("Testing load agent list (empty)...")

    with tempfile.TemporaryDirectory() as temp_dir:
        base_dir = Path(temp_dir)
        settings = create_default_settings()
        loader = AgentLoader(base_dir, settings)

        agents = loader._load_agent_list()

        assert agents == []

        print("✓ Load agent list (empty) works correctly")


async def test_load_agent_list_with_file():
    """Test loading agent list from valid agents.yaml."""
    print("Testing load agent list (with file)...")

    with tempfile.TemporaryDirectory() as temp_dir:
        base_dir = Path(temp_dir)
        agents_yaml = base_dir / "agents.yaml"
        agents_yaml.write_text("""agents:
  - name: test_agent
    enabled: true
    channels:
      - type: file
        identifier: test
        file_path: test.txt
    llm:
      mcp_url: http://localhost:8000/mcp
      auth_token: "test-token"
""")

        settings = create_default_settings()
        loader = AgentLoader(base_dir, settings)

        agents = loader._load_agent_list()

        assert len(agents) == 1
        assert agents[0]["name"] == "test_agent"
        assert agents[0]["enabled"] is True

        print("✓ Load agent list (with file) works correctly")


async def test_load_agent_list_disabled_agent():
    """Test that disabled agents are excluded."""
    print("Testing load agent list (disabled agent)...")

    with tempfile.TemporaryDirectory() as temp_dir:
        base_dir = Path(temp_dir)
        agents_yaml = base_dir / "agents.yaml"
        agents_yaml.write_text("""agents:
  - name: enabled_agent
    enabled: true
  - name: disabled_agent
    enabled: false
""")

        settings = create_default_settings()
        loader = AgentLoader(base_dir, settings)

        configs = await loader.load_agent_configs()

        assert len(configs) == 1
        assert configs[0].name == "enabled_agent"

        print("✓ Load agent list (disabled agent) works correctly")


async def test_create_llm_clients():
    """Test LLM client creation."""
    print("Testing create_llm_clients...")

    with tempfile.TemporaryDirectory() as temp_dir:
        base_dir = Path(temp_dir)
        settings = create_default_settings()
        loader = AgentLoader(base_dir, settings)

        agent_config = AgentConfig(
            name="test_agent",
            llm=LlmConfig(
                mcp_url="http://localhost:8000/mcp",
                auth_token="test-token",
                triage_model="qwen2.5-coder:7b",
                capable_model="qwen2.5-coder:7b",
            ),
        )

        triage_llm, capable_llm = loader._create_llm_clients(agent_config)

        assert triage_llm.mcp_url == "http://localhost:8000/mcp"
        assert triage_llm.auth_token == "test-token"
        assert triage_llm.model == "qwen2.5-coder:7b"
        assert triage_llm.max_tokens == 50

        assert capable_llm.mcp_url == "http://localhost:8000/mcp"
        assert capable_llm.auth_token == "test-token"
        assert capable_llm.model == "qwen2.5-coder:7b"
        assert capable_llm.max_tokens == 500

        print("✓ Create LLM clients works correctly")


async def test_create_channel_file():
    """Test file channel creation."""
    print("Testing create_channel (file)...")

    with tempfile.TemporaryDirectory() as temp_dir:
        base_dir = Path(temp_dir)
        settings = create_default_settings()
        loader = AgentLoader(base_dir, settings)

        channel_config = {
            "type": "file",
            "identifier": "test",
            "file_path": "test.txt",
            "name": "TestChannel",
        }

        channel = loader._create_channel(channel_config)

        assert channel is not None
        assert channel.type == "file"
        assert channel.identifier == "test"
        assert channel.file_path.name == "test.txt"

        print("✓ Create channel (file) works correctly")


async def test_create_channel_missing_path():
    """Test file channel creation fails without path."""
    print("Testing create_channel (missing path)...")

    with tempfile.TemporaryDirectory() as temp_dir:
        base_dir = Path(temp_dir)
        settings = create_default_settings()
        loader = AgentLoader(base_dir, settings)

        channel_config = {
            "type": "file",
            "identifier": "test",
        }

        channel = loader._create_channel(channel_config)

        assert channel is None

        print("✓ Create channel (missing path) works correctly")


async def test_create_channel_unsupported():
    """Test unsupported channel type."""
    print("Testing create_channel (unsupported)...")

    with tempfile.TemporaryDirectory() as temp_dir:
        base_dir = Path(temp_dir)
        settings = create_default_settings()
        loader = AgentLoader(base_dir, settings)

        channel_config = {
            "type": "telegram",
            "identifier": "test",
        }

        channel = loader._create_channel(channel_config)

        assert channel is None

        print("✓ Create channel (unsupported) works correctly")


async def test_load_all_agents_empty():
    """Test loading all agents when none defined."""
    print("Testing load_all_agents (empty)...")

    with tempfile.TemporaryDirectory() as temp_dir:
        base_dir = Path(temp_dir)
        settings = create_default_settings()
        loader = AgentLoader(base_dir, settings)

        agents = await loader.load_all_agents()

        assert agents == []

        print("✓ Load all agents (empty) works correctly")


async def test_load_all_agents_with_config():
    """Test loading all agents with valid config."""
    print("Testing load_all_agents (with config)...")

    with tempfile.TemporaryDirectory() as temp_dir:
        base_dir = Path(temp_dir)

        # Create agents.yaml
        agents_yaml = base_dir / "agents.yaml"
        agents_yaml.write_text("""agents:
  - name: test_agent
    enabled: true
    channels:
      - type: file
        identifier: test
        file_path: test.txt
    llm:
      mcp_url: http://localhost:8000/mcp
      auth_token: "test-token"
      triage_model: qwen2.5-coder:7b
      capable_model: qwen2.5-coder:7b
""")

        # Create test file
        test_file = base_dir / "test.txt"
        test_file.write_text("test message\n")

        settings = create_default_settings()
        loader = AgentLoader(base_dir, settings)

        agents = await loader.load_all_agents()

        assert len(agents) == 1
        assert agents[0].agent_name == "test_agent"
        assert len(agents[0].channels) == 1

        print("✓ Load all agents (with config) works correctly")


async def main():
    """Run all tests."""
    print("Running AgentLoader tests...\n")

    tests = [
        test_loader_initialization,
        test_load_agent_list_empty,
        test_load_agent_list_with_file,
        test_load_agent_list_disabled_agent,
        test_create_llm_clients,
        test_create_channel_file,
        test_create_channel_missing_path,
        test_create_channel_unsupported,
        test_load_all_agents_empty,
        test_load_all_agents_with_config,
    ]

    for test in tests:
        try:
            await test()
        except Exception as e:
            print(f"✗ Test failed: {e}")
            import traceback

            traceback.print_exc()
            return 1
        print()

    print("All tests passed! ✓")
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
