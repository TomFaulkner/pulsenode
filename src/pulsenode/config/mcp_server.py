from pydantic import SecretStr
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    mcp_jwt_secret: SecretStr
    mcp_jwt_issuer: str
    mcp_jwt_audience: str
    mcp_jwt_algorithm: str = "HS256"
    mcp_server_name: str = "pulsenode-tools"


settings = Settings()
