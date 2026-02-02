from dataclasses import dataclass
from pydantic import BaseModel


class TriageResponse(BaseModel):
    needed: bool
    reason: str


@dataclass(frozen=True)
class LlmMcp:
    mcp_url: str
    auth_token: str
    max_tokens: int

    async def generate_triage_response(self, prompt: str) -> TriageResponse:
        # Mock implementation of LLM response generation via MCP
        return TriageResponse(needed=True, reason="Mock reason")

    async def generate_response(self, prompt: str) -> str:
        return "tool:hello_world"
