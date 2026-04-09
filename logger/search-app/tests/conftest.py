"""
Pytest configuration and shared fixtures for search-app tests.
"""

import os
import pytest


# Test configuration
TEST_USER_ID = "Participant1"
DEFAULT_APP_URL = "http://localhost:7001"


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "requires_app: mark test as requiring the Flask app to be running"
    )
    config.addinivalue_line(
        "markers", "bfcache: mark test as specifically testing BFCache behavior"
    )


@pytest.fixture(scope="session")
def test_user_id():
    """Return a valid test user ID."""
    return os.environ.get("TEST_USER_ID", TEST_USER_ID)


@pytest.fixture(scope="session")
def base_url():
    """Return the base URL for the Flask app."""
    return os.environ.get("SEARCH_APP_URL", DEFAULT_APP_URL)
