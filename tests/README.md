# Tests

This directory contains the pytest-based test suite for the pulsenode project.

## Structure

```
tests/
├── __init__.py
├── conftest.py                 # Global pytest configuration and fixtures
├── unit/                      # Unit tests (fast, isolated)
│   ├── agent/                  # Tests for agent functionality
│   ├── mcp/clients/           # Tests for MCP clients
│   ├── mcp/servers/           # Tests for MCP servers
│   └── tools/                 # Tests for tools and configuration
└── integration/               # Integration tests (slower, use external services)
    └── test_integration.py
```

## Running Tests

### Quick Start
```bash
# Install test dependencies
source .venv/bin/activate && uv sync --group dev

# Run all unit tests
python -m pytest tests/unit -v

# Run all integration tests
python -m pytest tests/integration -v

# Run tests with coverage
python -m pytest --cov=src/pulsenode --cov-report=term-missing

# Use the test runner script
./run_tests.py
```

### Test Categories

- **Unit Tests** (`@pytest.mark.unit`): Fast, isolated tests for individual components
- **Integration Tests** (`@pytest.mark.integration`): Slower tests that verify component interaction
- **Slow Tests** (`@pytest.mark.slow`): Tests that take significant time or resources

### Selective Test Execution

```bash
# Run only unit tests
python -m pytest -m unit

# Run only integration tests  
python -m pytest -m integration

# Skip slow tests
python -m pytest -m "not slow"

# Run specific test file
python -m pytest tests/unit/mcp/clients/test_ollama_client.py -v
```

## Writing New Tests

1. Place unit tests in `tests/unit/` in the appropriate subdirectory
2. Use descriptive test function names starting with `test_`
3. Use `@pytest.mark.unit` for unit tests
4. Use `@pytest.mark.asyncio` for async test functions
5. Mock external dependencies using `unittest.mock`
6. Follow the existing patterns in the test files

### Test Example

```python
import pytest
from unittest.mock import AsyncMock, patch

from pulsenode.module import ClassToTest

class TestClassName:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_function_name(self):
        # Arrange
        mock_dependency = AsyncMock()
        
        # Act
        result = await function_being_tested()
        
        # Assert
        assert result.expected_value == "expected"
        mock_dependency.assert_called_once()
```

## Coverage

The test suite is configured to generate coverage reports. Run:

```bash
python -m pytest --cov=src/pulsenode --cov-report=html
```

This will generate an HTML report in `htmlcov/` directory.

## Notes

- All tests automatically add `src/` to Python path via `conftest.py`
- Tests use pytest-asyncio for async function support
- Mock objects are used to isolate units from external dependencies
- Integration tests are marked as `slow` and skipped by default fast test runs