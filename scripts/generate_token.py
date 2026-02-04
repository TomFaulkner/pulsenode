from datetime import datetime, timedelta, UTC
from typing import TypedDict

import jwt

from pulsenode.config import mcp_server_settings as settings

# class JWTTokenBody(BaseModel):
#     sub: str
#     aud: str
#     exp: datetime
#     nbf: datetime | None = None
#     iss: str
#     iat: datetime
#


class MCPTokenData(TypedDict):
    pass


def create_access_token(
    sub: str, data: MCPTokenData, expires_delta: timedelta | None = None
) -> str:
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(minutes=15)
    now = datetime.now(UTC)
    body = {
        "sub": sub,
        "iat": now,
        "nbf": now,
        "iss": settings.mcp_jwt_issuer,
        "exp": expire,
        "aud": settings.mcp_jwt_audience,
    } | data

    encoded_jwt = jwt.encode(
        body,
        settings.mcp_jwt_secret.get_secret_value(),
        algorithm=settings.mcp_jwt_algorithm,
    )
    return encoded_jwt


print("Generating MCP access token...")
token = create_access_token(sub="test_client", data={})
print("MCP Access Token:")
print(token)
