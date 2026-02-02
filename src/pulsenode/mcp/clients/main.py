import asyncio

from fastmcp import Client
from httpx import AsyncClient

# HTTP server

# Local Python script
# client = Client("my_mcp_server.py")


async def get_token():
    async with AsyncClient() as http_client:
        response = await http_client.post(
            "http://localhost:8000/api/mcp_token/create_token",
        )
        response.raise_for_status()
        token_data = response.json()
        return token_data["access_token"]


async def main():
    token = await get_token()
    client = Client("http://localhost:8000/mcp", auth=token)
    async with client:
        # Basic server interaction
        print("Pinging server...")
        # await client.ping()

        # List available operations
        tools = await client.list_tools()
        print(tools)
        resources = await client.list_resources()
        prompts = await client.list_prompts()

        # Execute operations
        result = await client.call_tool("greet", {"name": "World"})
        print(result)


asyncio.run(main())

