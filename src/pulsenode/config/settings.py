from pydantic import Field, BeforeValidator
from typing import Literal, Annotated
from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path


def empty_str_to_none(v):
    """Convert empty strings to None for optional fields."""
    if v == "":
        return None
    return v


# Type for optional string fields that might be empty in .env
OptionalStr = Annotated[str | None, BeforeValidator(empty_str_to_none)]
# Type for optional int fields that might be empty in .env
OptionalInt = Annotated[int | None, BeforeValidator(empty_str_to_none)]


class LLMProxyConfig(BaseSettings):
    # Note: all keys will be prefixed with "llm_proxy_" in environment variables
    enabled: bool = Field(default=False, description="Enable LLM proxy functionality")
    provider_default: Literal["ollama", "llamacpp"] = Field(
        default="ollama", description="Default LLM provider (ollama or llamacpp)"
    )
    endpoint: str = Field(
        default="http://localhost:11434", description="Base URL for the LLM provider"
    )
    model: str = Field(default="llama3", description="Default model to use")
    api_key: OptionalStr = Field(
        default=None, description="API key for authentication (if required)"
    )
    temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Default temperature for text generation",
    )
    max_tokens: OptionalInt = Field(
        default=None, description="Maximum number of tokens to generate (if supported)"
    )
    stream: bool = Field(default=True, description="Enable streaming responses")

    model_config = SettingsConfigDict(
        env_prefix="llm_proxy_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


class Settings(BaseSettings):
    app_name: str = "PulseNode"

    heartbeat_interval_seconds: int = 30
    pulsenode_directory: str = Field(
        "~/.pulsenode",
        description="Directory for PulseNode data storage",
    )

    # Agent and memory configuration
    default_agent_name: str = Field(
        "default_agent",
        description="Default agent name when none specified",
    )
    default_session_mode: str = Field(
        "time_based",
        description="Default session mode (time_based or thread_based)",
    )
    default_time_granularity: str = Field(
        "weekly",
        description="Default time granularity (daily or weekly)",
    )
    max_session_size_kb: int = Field(
        100,
        description="Maximum session size before archiving (KB)",
    )
    min_messages_threshold: int = Field(
        5,
        description="Minimum messages before considering session archive",
    )

    # Memory limits
    max_agent_memory_chars: int = Field(
        2000,
        description="Maximum agent memory characters to include in context",
    )
    max_channel_memory_chars: int = Field(
        1500,
        description="Maximum channel memory characters to include in context",
    )
    max_session_summary_chars: int = Field(
        800,
        description="Maximum session summary characters to include in context",
    )
    max_recent_messages: int = Field(
        10,
        description="Maximum recent messages to include in context",
    )

    # Tool configuration
    tools_enabled: bool = Field(
        default=True,
        description="Enable tool system for agents",
    )
    default_workspace_dir: str = Field(
        "workspace",
        description="Default workspace directory name within agent directory",
    )
    default_approval_timeout: int = Field(
        300,
        description="Default approval timeout in seconds",
    )
    max_file_size_kb: int = Field(
        100,
        description="Maximum file size to read directly (KB)",
    )

    llm_proxy: LLMProxyConfig = Field(
        default_factory=LLMProxyConfig,
        description="Configuration for LLM proxy functionality",
    )
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


def create_default_settings() -> Settings:
    """Create default settings with required parameters."""
    return Settings(
        pulsenode_directory=str(Path.home() / ".pulsenode"),
        default_agent_name="default_agent",
        default_session_mode="time_based",
        default_time_granularity="weekly",
        max_session_size_kb=100,
        min_messages_threshold=5,
        max_agent_memory_chars=2000,
        max_channel_memory_chars=1500,
        max_session_summary_chars=800,
        max_recent_messages=10,
        tools_enabled=True,
        default_workspace_dir="workspace",
        default_approval_timeout=300,
        max_file_size_kb=100,
    )


settings = create_default_settings()
