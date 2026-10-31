import pytest
from app.auth import require_user
from app.main import app


@pytest.fixture(autouse=True)
def isolate_settings_cache():
    from app.config import settings
    settings.cache_clear()
    yield
    settings.cache_clear()


@pytest.fixture
def signed_in():
    """Existing endpoint tests exercise their handlers as an authenticated user."""
    app.dependency_overrides[require_user] = lambda: {'id': 1, 'name': 'Test', 'email': 'test@example.com'}
    yield
    app.dependency_overrides.pop(require_user, None)
