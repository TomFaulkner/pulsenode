from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "PulseNode"

    heartbeat_interval_seconds: int = 30


settings = Settings()
