"""Shared test fixtures."""
import pytest

from app.core.db import dispose_engine


@pytest.fixture(autouse=True)
async def _dispose_engine_between_tests():
    """pytest-asyncio gives each test its own event loop, but the engine is
    cached in a module global. Without disposing it, the second DB-touching
    test inherits connections bound to a loop that has already closed."""
    yield
    await dispose_engine()
