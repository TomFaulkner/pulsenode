from pydantic import Field, BeforeValidator
from typing import Literal, Annotated
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    enabled: bool = Field(False, description="Enable LLM proxy functionality")
    provider_default: Literal["ollama", "llamacpp"] = Field(
        "ollama", description="Default LLM provider (ollama or llamacpp)"
    )
    endpoint: str = Field(
        "http://localhost:11434", description="Base URL for the LLM provider"
    )
    model: str = Field("llama3", description="Default model to use")
    api_key: OptionalStr = Field(
        None, description="API key for authentication (if required)"
    )
    temperature: float = Field(
        0.7, ge=0.0, le=1.0, description="Default temperature for text generation"
    )
    max_tokens: OptionalInt = Field(
        None, description="Maximum number of tokens to generate (if supported)"
    )
    stream: bool = Field(True, description="Enable streaming responses")

    model_config = SettingsConfigDict(
        env_prefix="llm_proxy_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


class Settings(BaseSettings):
    app_name: str = "PulseNode"

    heartbeat_interval_seconds: int = 30

    llm_proxy: LLMProxyConfig = Field(
        default_factory=LLMProxyConfig,
        description="Configuration for LLM proxy functionality",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
