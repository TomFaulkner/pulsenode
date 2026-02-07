"""Agent Configuration Management for PulseNode.

Handles YAML configuration for agents with cross-agent access control and tool settings.
"""

import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pulsenode.agent.sessions import SessionConfig, TimeGranularity, SessionMode


@dataclass
class ShellConfig:
    """Shell tool configuration."""

    enabled: bool = True
    allowlist: list[str] = field(default_factory=list)
    container_enabled: bool = True
    default_container_image: str = "debian:latest"

    def __post_init__(self):
        if not self.allowlist:
            self.allowlist = [
                "ls",
                "cat",
                "grep",
                "find",
                "wc",
                "head",
                "tail",
                "sort",
                "uniq",
                "cut",
                "awk",
                "sed",
                "tr",
                "df",
                "du",
                "ps",
                "top",
                "free",
                "whoami",
                "pwd",
                "date",
                "uptime",
                "tree",
                "which",
                "file",
                "stat",
                "python",
                "python3",
                "git",
                "curl",
                "wget",
                "node",
                "npm",
                "pip",
                "pip3",
            ]


@dataclass
class FileConfig:
    """File tool configuration."""

    enabled: bool = True
    allowed_directories: list[str] = field(default_factory=list)
    access_home_directory: bool = False
    max_file_size_kb: int = 100


@dataclass
class HttpConfig:
    """HTTP tool configuration."""

    enabled: bool = True
    allowed_hosts: list[str] = field(default_factory=list)
    require_confirmation: bool = True


@dataclass
class ToolsConfig:
    """Tools configuration for an agent."""

    enabled: bool = True
    shell: ShellConfig = field(default_factory=ShellConfig)
    file: FileConfig = field(default_factory=FileConfig)
    http: HttpConfig = field(default_factory=HttpConfig)
    approval_timeout_seconds: int = 300


@dataclass
class AgentConfig:
    """Configuration for an agent."""

    name: str
    purpose: str = ""
    session_config: SessionConfig = field(default_factory=SessionConfig)
    can_access_other_agents: list[str] = field(default_factory=list)
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)
    tools: ToolsConfig = field(default_factory=ToolsConfig)


class AgentConfigManager:
    """Manages agent configuration files."""

    def __init__(self, config_dir: Path):
        """Initialize with configuration directory."""
        self.config_dir = Path(config_dir)

    async def load_agent_config(self, agent_name: str) -> AgentConfig:
        """Load agent configuration from YAML file."""
        config_file = self.config_dir / "agents" / agent_name / "config.yaml"

        if not config_file.exists():
            # Return default config
            return AgentConfig(name=agent_name)

        try:
            with open(config_file, "r") as f:
                data = yaml.safe_load(f)

            # Parse session config
            session_config_data = data.get("session_config", {})
            session_config = SessionConfig(
                session_mode=SessionMode(
                    session_config_data.get("session_mode", "time_based")
                ),
                time_granularity=TimeGranularity(
                    session_config_data.get("time_granularity", "weekly")
                ),
                min_messages_threshold=session_config_data.get(
                    "min_messages_threshold", 5
                ),
                max_session_size_kb=session_config_data.get("max_session_size_kb", 100),
                can_access_other_agents=session_config_data.get(
                    "can_access_other_agents", []
                ),
            )

            # Parse tools config
            tools_data = data.get("tools", {})
            shell_data = tools_data.get("shell", {})
            file_data = tools_data.get("file", {})
            http_data = tools_data.get("http", {})

            shell_config = ShellConfig(
                enabled=shell_data.get("enabled", True),
                allowlist=shell_data.get("allowlist", []),
                container_enabled=shell_data.get("container_enabled", True),
                default_container_image=shell_data.get(
                    "default_container_image", "debian:latest"
                ),
            )

            file_config = FileConfig(
                enabled=file_data.get("enabled", True),
                allowed_directories=file_data.get("allowed_directories", []),
                access_home_directory=file_data.get("access_home_directory", False),
                max_file_size_kb=file_data.get("max_file_size_kb", 100),
            )

            http_config = HttpConfig(
                enabled=http_data.get("enabled", True),
                allowed_hosts=http_data.get("allowed_hosts", []),
                require_confirmation=http_data.get("require_confirmation", True),
            )

            tools_config = ToolsConfig(
                enabled=tools_data.get("enabled", True),
                shell=shell_config,
                file=file_config,
                http=http_config,
                approval_timeout_seconds=tools_data.get(
                    "approval_timeout_seconds", 300
                ),
            )

            return AgentConfig(
                name=agent_name,
                purpose=data.get("purpose", ""),
                session_config=session_config,
                can_access_other_agents=data.get("can_access_other_agents", []),
                enabled=data.get("enabled", True),
                metadata=data.get("metadata", {}),
                tools=tools_config,
            )

        except Exception as e:
            # Log error and return default config
            from structlog import get_logger

            logger = get_logger(__name__)
            logger.error(
                "failed_to_load_agent_config", agent_name=agent_name, error=str(e)
            )
            return AgentConfig(name=agent_name)

    async def save_agent_config(self, config: AgentConfig) -> None:
        """Save agent configuration to YAML file."""
        config_file = self.config_dir / "agents" / config.name / "config.yaml"
        config_file.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "name": config.name,
            "purpose": config.purpose,
            "session_config": {
                "session_mode": config.session_config.session_mode.value,
                "time_granularity": config.session_config.time_granularity.value,
                "min_messages_threshold": config.session_config.min_messages_threshold,
                "max_session_size_kb": config.session_config.max_session_size_kb,
                "can_access_other_agents": config.session_config.can_access_other_agents,
            },
            "can_access_other_agents": config.can_access_other_agents,
            "enabled": config.enabled,
            "metadata": config.metadata,
            "tools": {
                "enabled": config.tools.enabled,
                "shell": {
                    "enabled": config.tools.shell.enabled,
                    "allowlist": config.tools.shell.allowlist,
                    "container_enabled": config.tools.shell.container_enabled,
                    "default_container_image": config.tools.shell.default_container_image,
                },
                "file": {
                    "enabled": config.tools.file.enabled,
                    "allowed_directories": config.tools.file.allowed_directories,
                    "access_home_directory": config.tools.file.access_home_directory,
                    "max_file_size_kb": config.tools.file.max_file_size_kb,
                },
                "http": {
                    "enabled": config.tools.http.enabled,
                    "allowed_hosts": config.tools.http.allowed_hosts,
                    "require_confirmation": config.tools.http.require_confirmation,
                },
                "approval_timeout_seconds": config.tools.approval_timeout_seconds,
            },
        }

        # Remove empty sections
        if not data["session_config"]["can_access_other_agents"]:
            del data["session_config"]["can_access_other_agents"]

        with open(config_file, "w") as f:
            yaml.dump(data, f, default_flow_style=False, indent=2)

    async def load_agent_purpose(self, agent_name: str) -> str:
        """Load agent purpose from purpose.md file."""
        purpose_file = self.config_dir / "agents" / agent_name / "purpose.md"

        if purpose_file.exists():
            return purpose_file.read_text().strip()

        return ""

    async def save_agent_purpose(self, agent_name: str, purpose: str) -> None:
        """Save agent purpose to purpose.md file."""
        purpose_file = self.config_dir / "agents" / agent_name / "purpose.md"
        purpose_file.parent.mkdir(parents=True, exist_ok=True)
        purpose_file.write_text(purpose.strip())

    async def list_agents(self) -> list[str]:
        """List all available agents."""
        agents_dir = self.config_dir / "agents"

        if not agents_dir.exists():
            return []

        agents = []
        for item in agents_dir.iterdir():
            if item.is_dir():
                config_file = item / "config.yaml"
                if config_file.exists():
                    agents.append(item.name)

        return agents

    async def check_agent_access(self, from_agent: str, to_agent: str) -> bool:
        """Check if from_agent can access to_agent's data."""
        # Same agent always has access
        if from_agent == to_agent:
            return True

        # Load from_agent config
        config = await self.load_agent_config(from_agent)

        # Check if to_agent is in whitelist
        return to_agent in config.can_access_other_agents

    async def get_accessible_agents(self, agent_name: str) -> list[str]:
        """Get list of agents that this agent can access."""
        config = await self.load_agent_config(agent_name)
        accessible = [agent_name]  # Always can access self

        # Add whitelisted agents that exist
        all_agents = await self.list_agents()
        for whitelist_agent in config.can_access_other_agents:
            if whitelist_agent in all_agents:
                accessible.append(whitelist_agent)

        return accessible
