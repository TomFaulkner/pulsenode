"""Agent Loader for PulseNode.

Loads agents from configuration and instantiates them with proper channels and LLM clients.
"""

import yaml
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from pulsenode.config.settings import Settings
from pulsenode.agent.agent_config import AgentConfigManager, AgentConfig
from pulsenode.agent.llm_mcp import LlmMcp
from pulsenode.agent.channels import FileChannelMcp

if TYPE_CHECKING:
    from pulsenode.agent.main import Agent

logger = structlog.get_logger(__name__)


class AgentLoader:
    """Loads and instantiates agents from configuration."""

    def __init__(self, config_dir: Path, settings: Settings):
        """Initialize agent loader.

        Args:
            config_dir: Base configuration directory (e.g., ~/.pulsenode)
            settings: Application settings
        """
        self.config_dir = Path(config_dir)
        self.settings = settings
        self.config_manager = AgentConfigManager(self.config_dir)

    def _load_agent_list(self) -> list[dict[str, Any]]:
        """Load the agent list from agents.yaml."""
        agents_file = self.config_dir / "agents.yaml"

        if not agents_file.exists():
            logger.warning("agents_yaml_not_found", path=str(agents_file))
            return []

        try:
            with open(agents_file, "r") as f:
                data = yaml.safe_load(f)
                return data.get("agents", [])
        except Exception as e:
            logger.error("failed_to_load_agents_yaml", error=str(e))
            return []

    def _create_channel(self, channel_config: dict[str, Any]) -> FileChannelMcp | None:
        """Create a channel instance from configuration.

        Args:
            channel_config: Channel configuration dict

        Returns:
            Channel instance or None if creation fails
        """
        channel_type = channel_config.get("type", "file")

        if channel_type == "file":
            file_path = channel_config.get("file_path", "")
            if not file_path:
                logger.warning("file_channel_missing_path")
                return None

            return FileChannelMcp(
                file_path=Path(file_path),
                name=channel_config.get(
                    "name", f"file-{channel_config.get('identifier', 'default')}"
                ),
                type="file",
                identifier=channel_config.get("identifier", ""),
                sleep_seconds=channel_config.get("sleep_seconds", 0.2),
            )

        logger.warning("unsupported_channel_type", channel_type=channel_type)
        return None

    def _create_llm_clients(self, agent_config: AgentConfig) -> tuple[LlmMcp, LlmMcp]:
        """Create triage and capable LLM clients for an agent.

        Args:
            agent_config: Agent configuration

        Returns:
            Tuple of (triage_llm, capable_llm)
        """
        llm = agent_config.llm

        triage_llm = LlmMcp(
            mcp_url=llm.mcp_url,
            auth_token=llm.auth_token,
            max_tokens=llm.triage_max_tokens,
            model=llm.triage_model,
            temperature=llm.triage_temperature,
        )

        capable_llm = LlmMcp(
            mcp_url=llm.mcp_url,
            auth_token=llm.auth_token,
            max_tokens=llm.capable_max_tokens,
            model=llm.capable_model,
            temperature=llm.temperature,
        )

        return triage_llm, capable_llm

    async def load_agent_configs(self) -> list[AgentConfig]:
        """Load configurations for all agents defined in agents.yaml.

        Returns:
            List of agent configurations
        """
        agent_list = self._load_agent_list()
        configs = []

        for agent_def in agent_list:
            agent_name = agent_def.get("name")
            if not agent_name:
                logger.warning("agent_definition_missing_name")
                continue

            if not agent_def.get("enabled", True):
                logger.info("agent_disabled_skipping", agent_name=agent_name)
                continue

            config = await self.config_manager.load_agent_config(agent_name)

            if not config.enabled:
                logger.info("agent_config_disabled_skipping", agent_name=agent_name)
                continue

            config.llm.mcp_url = agent_def.get("llm", {}).get(
                "mcp_url", config.llm.mcp_url
            )
            config.llm.auth_token = agent_def.get("llm", {}).get(
                "auth_token", config.llm.auth_token
            )
            config.llm.triage_model = agent_def.get("llm", {}).get(
                "triage_model", config.llm.triage_model
            )
            config.llm.capable_model = agent_def.get("llm", {}).get(
                "capable_model", config.llm.capable_model
            )

            channels_data = agent_def.get("channels", [])
            for ch_data in channels_data:
                from pulsenode.agent.agent_config import ChannelDefinition

                config.channels.append(
                    ChannelDefinition(
                        type=ch_data.get("type", "file"),
                        identifier=ch_data.get("identifier", ""),
                        file_path=ch_data.get("file_path", ""),
                        sleep_seconds=ch_data.get("sleep_seconds", 0.2),
                    )
                )

            configs.append(config)
            logger.info("loaded_agent_config", agent_name=agent_name)

        return configs

    async def create_agent(
        self,
        agent_config: AgentConfig,
        triage_llm: LlmMcp,
        capable_llm: LlmMcp,
    ) -> "Agent":
        """Create an Agent instance from configuration.

        Args:
            agent_config: Agent configuration
            triage_llm: Triage LLM client
            capable_llm: Capable LLM client

        Returns:
            Configured Agent instance
        """
        from pulsenode.agent.main import Agent, Context
        from datetime import datetime, UTC

        channels = []
        for ch in agent_config.channels:
            channel = self._create_channel(
                {
                    "type": ch.type,
                    "identifier": ch.identifier,
                    "file_path": ch.file_path,
                    "sleep_seconds": ch.sleep_seconds,
                    "name": f"{ch.type}-{ch.identifier}",
                }
            )
            if channel:
                channels.append(channel)

        if not channels:
            logger.warning("no_channels_for_agent", agent_name=agent_config.name)

        context = Context(now=datetime.now(UTC))

        agent = Agent(
            triage_llm=triage_llm,
            capable_llm=capable_llm,
            context=context,
            channels=channels,
            agent_name=agent_config.name,
            pulsenode_dir=self.config_dir,
            settings=self.settings,
        )

        return agent

    async def load_all_agents(self) -> list["Agent"]:
        """Load all enabled agents from configuration.

        Returns:
            List of configured Agent instances
        """
        configs = await self.load_agent_configs()
        agents = []

        for config in configs:
            triage_llm, capable_llm = self._create_llm_clients(config)
            agent = await self.create_agent(config, triage_llm, capable_llm)
            agents.append(agent)
            logger.info("agent_loaded", agent_name=config.name)

        logger.info("all_agents_loaded", count=len(agents))
        return agents
