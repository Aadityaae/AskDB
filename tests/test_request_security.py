"""Regression checks for resource limits and authentication before parsing files."""
from fastapi.testclient import TestClient
import pytest
from app.main import app


@pytest.mark.parametrize('route', ['/v1/sources', '/v1/transcribe'])
def test_unauthenticated_files_are_not_parsed(route):
    consumed = []

    def body():
        consumed.append(True)
        yield b'malformed multipart data'

    with TestClient(app) as client:
        response = client.post(route, headers={'content-type': 'multipart/form-data; boundary=audit'}, content=body())
    assert response.status_code == 401
    assert consumed == []


def test_voice_body_limit_applies_before_parsing():
    with TestClient(app) as client:
        response = client.post('/v1/transcribe', content=b'x', headers={'content-length': str(8 * 1024 * 1024)})
    assert response.status_code == 413


def test_json_body_limit_counts_chunked_content():
    with TestClient(app) as client:
        response = client.post('/v1/auth/login', headers={'content-type': 'application/json'},
                               content=iter([b'{"email":"', b'x' * (129 * 1024), b'"}']))
    assert response.status_code == 413


def test_voice_rejects_multiple_files(signed_in):
    with TestClient(app) as client:
        response = client.post('/v1/transcribe', files=[('audio', ('a.wav', b'a')), ('audio', ('b.wav', b'b'))])
    assert response.status_code == 400


def test_voice_rejects_unexpected_form_fields(signed_in):
    with TestClient(app) as client:
        response = client.post('/v1/transcribe', files={'audio': ('a.wav', b'a')}, data={'unexpected': 'field'})
    assert response.status_code == 400


def test_api_errors_are_not_cacheable_and_have_security_headers():
    with TestClient(app) as client:
        response = client.get('/v1/auth/me')
    assert response.status_code == 401
    assert response.headers['cache-control'] == 'no-store'
    assert response.headers['x-content-type-options'] == 'nosniff'
    assert response.headers['x-frame-options'] == 'DENY'


def test_busy_query_is_rejected_without_queueing(signed_in, monkeypatch):
    from app import main
    class Busy:
        def acquire(self, **kwargs):
            return False
    monkeypatch.setattr(main, 'query_capacity', Busy())
    with TestClient(app) as client:
        response = client.post('/v1/query', json={'question': 'Count the records'})
    assert response.status_code == 429 and response.headers['retry-after'] == '2'
