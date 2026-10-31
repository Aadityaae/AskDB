from fastapi.testclient import TestClient
from app.main import app


def test_local_workspace_entry_preserves_host(monkeypatch):
    monkeypatch.setenv('WORKSPACE_URL', '')
    response = TestClient(app).get('/workspace?entry=signup', follow_redirects=False)
    assert response.headers['location'] == 'http://testserver:8501/?entry=signup'


def test_hosted_workspace_uses_configured_path(monkeypatch):
    monkeypatch.setenv('WORKSPACE_URL', '/workspace/')
    response = TestClient(app).get('/workspace?entry=signin', follow_redirects=False)
    assert response.headers['location'] == '/workspace/?entry=signin'


def test_workspace_rejects_arbitrary_entry():
    response = TestClient(app).get('/workspace?entry=https://example.com', follow_redirects=False)
    assert response.status_code == 422
