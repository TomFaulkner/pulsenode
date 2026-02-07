from typing import cast

from fastmcp import Context, FastMCP
from fastmcp.server.auth.providers.jwt import JWTVerifier
from fastmcp.server.middleware import Middleware, MiddlewareContext
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from structlog import BoundLogger, get_logger

from pulsenode.config import mcp_server_settings
from pulsenode.mcp.servers.llm_proxy import llm_proxy_mcp
from pulsenode.config.settings import settings


logger = cast("BoundLogger", get_logger(__name__).bind(service="mcp-server"))


class LoggingMiddleware(Middleware):
    """Middleware that logs all MCP operations."""

    async def on_message(self, context: MiddlewareContext, call_next):
        """Called for all MCP messages."""
        print(f"Processing {context.method} from {context.source}")

        # print("-----------", context.fastmcp_context.get_state("company_id"))
        result = await call_next(context)

        print(f"Completed {context.method}")
        return result


auth = JWTVerifier(
    public_key=mcp_server_settings.mcp_jwt_secret.get_secret_value(),
    issuer=mcp_server_settings.mcp_jwt_issuer,
    audience=mcp_server_settings.mcp_jwt_audience,
    algorithm=mcp_server_settings.mcp_jwt_algorithm,
)


mcp = FastMCP(mcp_server_settings.mcp_server_name)  # , auth=auth)
mcp.add_middleware(LoggingMiddleware())

# Add LLM proxy server if enabled
if settings.llm_proxy.enabled:
    logger.info("llm_proxy_enabled", message="Adding LLM proxy server to composition")
    mcp.mount(llm_proxy_mcp, prefix="llm")


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> PlainTextResponse:
    return PlainTextResponse("OK")


@mcp.tool
async def greet(name: str, ctx: Context) -> list[str]:
    return f"Hello, {name}"


if __name__ == "__main__":
    mcp.run(transport="http", port=8000)
