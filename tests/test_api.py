from fastapi.testclient import TestClient
from app.main import app
import pytest
pytestmark = pytest.mark.usefixtures('signed_in')


def test_health_survives_missing_services(monkeypatch):
    monkeypatch.setenv('DATABASE_URL', '')
    monkeypatch.setenv('READONLY_DATABASE_URL', '')
    from app.config import settings
    settings.cache_clear()
    with TestClient(app) as client:
        response = client.get('/v1/health')
        assert response.status_code == 200
        assert response.json()['api'] == 'ok'
        assert response.json()['database'] == 'unavailable'


def test_request_validation():
    with TestClient(app) as client:
        assert client.post('/v1/query', json={'question': ''}).status_code == 422


def test_schema_unavailable_returns_clean_error(monkeypatch):
    from app import main
    def unavailable():
        raise RuntimeError('Audit database unavailable')
    monkeypatch.setattr(main, 'extract_schema', unavailable)
    with TestClient(app) as client:
        response = client.get('/v1/schema')
        assert response.status_code == 503
        assert 'traceback' not in response.text.lower()
