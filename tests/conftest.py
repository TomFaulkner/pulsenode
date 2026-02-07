"""
Test configuration and fixtures.
"""

import asyncio
import pytest
import sys
import os

# Add src to path for all tests
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))


# Configure pytest for async tests
@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# Configure pytest-asyncio
@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"
