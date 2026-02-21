from abc import ABC, abstractmethod
from typing import Any


class ToolCallParser(ABC):
    """Abstract base class for tool call parsers."""

    @abstractmethod
    def parse(self, text: str) -> list[dict[str, Any]]:
        """
        Parse tool calls from LLM output text.

        Args:
            text: The raw output text from the LLM

        Returns:
            List of parsed tool call dicts in the parser's native format
        """
        pass

    @abstractmethod
    def format_tools_for_prompt(self, tools: list[str] | None = None) -> str:
        """
        Format tool definitions for inclusion in LLM prompt.

        Args:
            tools: List of tool names

        Returns:
            Formatted string describing available tools
        """
        pass

    @abstractmethod
    def format_tools_for_prompt_list(self) -> list[dict[str, Any]]:
        """
        Return tool definitions as a list for LLM API calls.

        Returns:
            List of tool definition dicts in OpenAI format
        """
        pass
