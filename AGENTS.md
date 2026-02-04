# Agent Development Guidelines

Development guidelines for agentic coding agents working on pulsenode codebase.

## Development Commands

### Environment Setup
```bash
source .venv/bin/activate && uv sync
```

### Code Quality
```bash
# Run linting (use this before committing)
ruff check src/
ruff check src/ --fix

# Check specific file
ruff check src/pulsenode/mcp/clients/ollama_client.py
python -m py_compile src/pulsenode/mcp/clients/ollama_client.py
```

### Testing
```bash
# Run pytest (recommended approach)
python -m pytest tests/unit -v
python -m pytest tests/integration -v

# Run tests with coverage
python -m pytest --cov=src/pulsenode --cov-report=term-missing

# Run specific test file
python -m pytest tests/unit/mcp/clients/test_ollama_client.py -v

# Run tests by marker
python -m pytest -m unit  # Unit tests only
python -m pytest -m integration  # Integration tests only
python -m pytest -m "not slow"  # Skip slow tests

# Use the test runner script
./run_tests.py

# Legacy standalone tests (still available)
python test_greet.py
python test_tools.py
python test_mcp.py
python test_complete_mcp.py
```

## Code Style Guidelines

### Import Organization
```python
# Standard library imports first
import asyncio
import logging
from datetime import datetime, UTC
from typing import Any, AsyncGenerator

# Third-party imports next  
import httpx
import pydantic
from fastmcp import FastMCP
from structlog import get_logger

# Local imports last
from pulsenode.config.settings import settings
from pulsenode.mcp.clients.ollama_client import OllamaClient
```

### Type Hints
- Use modern union syntax: `str | None` instead of `Optional[str]`
- Use specific imports: `from typing import AsyncGenerator` instead of `import typing`
- Use `list[dict[str, Any]]` for complex types
- Always annotate public methods and async functions

```python
async def chat(
    self,
    messages: list[dict[str, str]],
    stream: bool = True,
    max_tokens: int | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    pass
```

### Naming Conventions
- **Classes**: PascalCase (`OllamaClient`, `LLMProxyServer`)
- **Functions/Methods**: snake_case (`chat_with_llm`, `get_headers`)
- **Private methods**: prefix with underscore (`_get_headers`, `_parse_response`)
- **Constants**: UPPER_SNAKE_CASE (`DEFAULT_TIMEOUT`, `MAX_RETRIES`)

### Error Handling
```python
try:
    response = await self.session.post(url, json=data)
    response.raise_for_status()
    return response.json()
except httpx.ReadTimeout as e:
    logger.error("read_timeout", model=self.model, error=str(e))
    raise Exception(f"Read timeout occurred: {str(e)}")
except httpx.ConnectTimeout as e:
    logger.error("connect_timeout", model=self.model, error=str(e))
    raise Exception(f"Connect timeout occurred: {str(e)}")
except Exception as e:
    logger.error("request_error", model=self.model, error=str(e))
    raise Exception(f"Request failed: {str(e)}")
```

### Logging Patterns
```python
from structlog import get_logger

logger = get_logger(__name__)

logger.info("Initializing LLM proxy clients")
logger.warning("timeout_retrying", attempt=1, max_attempts=3, backoff=2.0)
logger.error("request_failed", provider=provider_name, error=str(e))
logger.debug("response_received", tokens=100, duration_ms=1500)
```

### Async/Await Patterns
- Use `async with` for resource management
- Implement async context managers for cleanup
- Use async generators for streaming responses

```python
async def __aenter__(self):
    return self

async def __aexit__(self, exc_type, exc_val, exc_tb):
    await self.close()

async def chat_stream(self, messages) -> AsyncGenerator[dict, None]:
    async with self.session.stream("POST", url, json=data) as response:
        async for line in response.aiter_lines():
            yield json.loads(line)
```

### Docstrings
```python
def get_metrics(self) -> dict[str, Any]:
    """Get performance metrics"""
    return self.metrics.copy()

async def chat_with_llm(
    self,
    messages: list[dict[str, str]],
    provider: str | None = None,
) -> str:
    """
    Chat with LLM through the proxy with full control over parameters.

    Args:
        messages: List of message dicts with 'role' and 'content' keys
        provider: LLM provider (ollama or llamacpp)

    Returns:
        Response content from the LLM

    Raises:
        Exception: If the request fails or times out
    """
    pass
```

## Project Structure Patterns

### Client Pattern
Follow established client pattern for new API integrations. Include metrics dict with "requests", "errors", "total_duration", "tokens_generated" keys. Use httpx.AsyncClient() with timeout configuration.

### MCP Server Pattern
For new MCP servers, follow FastMCP pattern. Create FastMCP instance, register handlers with @server.tool() decorator, implement _register_handlers() method.

## Testing Guidelines

### Test Files
- Tests are standalone Python scripts, not pytest
- Use `test_` prefix for test filenames
- Include `sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))` at the top

### Test Structure
```python
#!/usr/bin/env python3

import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from pulsenode.module import ClassToTest

async def test_feature():
    client = ClassToTest("test-config")
    result = await client.method()
    print(f"Result: {result}")

if __name__ == "__main__":
    asyncio.run(test_feature())
```

## Tools and Dependencies

### Core Dependencies
- `fastmcp`: MCP server framework
- `httpx`: Async HTTP client with timeout support
- `pydantic`: Data validation and serialization
- `structlog`: Structured logging
- `python-dotenv`: Environment variable management

### Development Tools
- `ruff`: Linting and formatting (configured in pyproject.toml)
- Python 3.14+ required (modern type hint support)

## Common Pitfalls to Avoid

1. **Don't use blocking I/O in async functions** - Always use async alternatives
2. **Don't import `*`** - Use specific imports
3. **Don't ignore timeout exceptions** - Handle them explicitly with retry logic
4. **Don't use `Optional[T]`** - Use modern `T | None` syntax
5. **Don't create clients without proper cleanup** - Implement `__aexit__` methods
6. **Don't log sensitive information** - Avoid logging API keys or tokens
7. **Don't use `raise Exception` for expected errors** - Use more specific exception types