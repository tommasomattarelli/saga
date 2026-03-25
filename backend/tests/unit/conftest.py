"""Override conftest fixtures that require DB for pure unit tests."""

import pytest


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    """No-op override — unit tests don't need DB."""
    yield


@pytest.fixture(autouse=True)
def clean_database():
    """No-op override — unit tests don't need DB."""
    yield
