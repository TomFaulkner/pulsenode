from pydantic import Field
from typing import Literal
from pydantic_settings import BaseSettings


class LLMProxyConfig(BaseSettings):
    # Note: all keys will be prefixed with "llm_proxy_" in environment variables
    enabled: bool = Field(False, description="Enable LLM proxy functionality")
    provider: Literal["ollama", "llamacpp"] = Field(
        "ollama", description="Default LLM provider (ollama or llamacpp)"
    )
    endpoint: str = Field(
        "http://localhost:11434", description="Base URL for the LLM provider"
    )
    model: str = Field("llama3", description="Default model to use")
    api_key: str | None = Field(
        None, description="API key for authentication (if required)"
    )
    temperature: float = Field(
        0.7, ge=0.0, le=1.0, description="Default temperature for text generation"
    )
    max_tokens: int | None = Field(
        None, description="Maximum number of tokens to generate (if supported)"
    )
    stream: bool = Field(True, description="Enable streaming responses")

    class Config:
        env_prefix = "llm_proxy_"
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


class Settings(BaseSettings):
    app_name: str = "PulseNode"

    heartbeat_interval_seconds: int = 30

    llm_proxy: LLMProxyConfig = Field(
        default_factory=lambda: LLMProxyConfig(
            enabled=False,
            provider="ollama",
            endpoint="http://localhost:11434",
            model="llama3",
            api_key=None,
            temperature=0.7,
            max_tokens=None,
            stream=True,
        ),
        description="Configuration for LLM proxy functionality",
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
