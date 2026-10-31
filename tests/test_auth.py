from datetime import timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app import auth, main
from app.config import settings
from app.db import AuthSession, Base, History, User
from app.models import QueryResponse


@pytest.fixture
def account_db(monkeypatch):
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine)
    monkeypatch.setattr(auth, 'metadata_session', factory)
    monkeypatch.setattr(main, 'metadata_session', factory)
    monkeypatch.setattr(main, 'metadata_engine', lambda: engine)
    settings.cache_clear()
    with TestClient(main.app) as client:
        yield client, factory
    settings.cache_clear()
    engine.dispose()


def register(client, email='a@example.com'):
    response = client.post('/v1/auth/signup', json={'name': 'Curious Ada', 'email': email, 'password': 'a long curious passphrase'})
    assert response.status_code == 201
    return response.json()


def headers(result):
    return {'Authorization': 'Bearer ' + result['token']}


def test_legacy_password_remains_valid_and_upgrades_on_login(account_db):
    import hashlib
    client, factory = account_db
    salt = 'a' * 32
    legacy = 'scrypt$' + salt + '$' + hashlib.scrypt(b'legacy secure password', salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    with factory() as db:
        db.add(User(name='Legacy account', email='legacy@example.com', password_hash=legacy))
        db.commit()
    response = client.post('/v1/auth/login', json={'email':'legacy@example.com', 'password':'legacy secure password'})
    assert response.status_code == 200
    with factory() as db:
        upgraded = db.scalar(select(User)).password_hash
    assert upgraded.startswith('scrypt$16384$8$5$')
    assert auth.password_matches('legacy secure password', upgraded)
    assert not auth.password_matches('incorrect password', upgraded)


def test_accounts_hash_secrets_validate_credentials_and_revoke_session(account_db):
    client, factory = account_db
    result = register(client, 'A@Example.com')
    assert result['user']['email'] == 'a@example.com'
    with factory() as db:
        user = db.scalar(select(User))
        assert user.password_hash.startswith('scrypt$')
        assert 'passphrase' not in user.password_hash
        assert db.get(AuthSession, auth.digest(result['token']))
        assert not db.get(AuthSession, result['token'])
    assert client.post('/v1/auth/signup', json={'name': 'Ada', 'email': 'a@example.com', 'password': 'long enough password'}).status_code == 409
    assert client.post('/v1/auth/signup', json={'name': 'Ada', 'email': 'bad', 'password': 'short'}).status_code == 422
    assert client.post('/v1/auth/login', json={'email': 'a@example.com', 'password': 'wrong'}).status_code == 401
    assert client.post('/v1/auth/login', json={'email': 'missing@example.com', 'password': 'wrong'}).status_code == 401
    login = client.post('/v1/auth/login', json={'email': 'a@example.com', 'password': 'a long curious passphrase'})
    assert login.status_code == 200
    assert client.get('/v1/auth/me', headers=headers(result)).status_code == 200
    assert client.post('/v1/auth/logout', headers=headers(result)).status_code == 200
    assert client.get('/v1/auth/me', headers=headers(result)).status_code == 401
    assert client.get('/v1/auth/me', headers=headers(login.json())).status_code == 200


def test_private_routes_reject_anonymous_and_expired_sessions(account_db):
    client, factory = account_db
    for path in ('/v1/schema', '/v1/data/employees', '/v1/history'):
        assert client.get(path).status_code == 401
    assert client.post('/v1/query', json={'question': 'How many employees?'}).status_code == 401
    assert client.post('/v1/transcribe').status_code == 401
    result = register(client)
    with factory() as db:
        login = db.get(AuthSession, auth.digest(result['token']))
        login.expires_at = auth.now() - timedelta(seconds=1)
        db.commit()
    assert client.get('/v1/auth/me', headers=headers(result)).status_code == 401


def test_history_and_feedback_are_owned_and_query_identity_cannot_be_forged(account_db, monkeypatch):
    client, factory = account_db
    first, second = register(client), register(client, 'b@example.com')
    response = QueryResponse(status='blocked', question='Private question', results=[{'count': 13}]).model_dump(mode='json')
    with factory() as db:
        record = History(session_id=f'user:{first["user"]["id"]}', question='Private question', status='blocked', response=response)
        db.add(record)
        db.commit()
        record_id = record.id
    assert client.get('/v1/history', headers=headers(first)).json()['total'] == 1
    assert 'results' not in client.get('/v1/history', headers=headers(first)).json()['items'][0]
    assert client.get(f'/v1/history/{record_id}', headers=headers(first)).json()['results'] == [{'count': 13}]
    assert client.get(f'/v1/history/{record_id}', headers=headers(second)).status_code == 404
    assert client.get(f'/v1/history/{record_id}').status_code == 401
    assert client.get('/v1/history', headers=headers(second)).json()['items'] == []
    assert client.post('/v1/feedback', headers=headers(second), json={'query_id': record_id, 'correct': True, 'comment': ''}).status_code == 404
    assert client.post('/v1/feedback', headers=headers(first), json={'query_id': record_id, 'correct': True, 'comment': ''}).status_code == 200
    captured = []
    def run(payload):
        captured.append(payload.session_id)
        return QueryResponse(status='blocked', question=payload.question)
    monkeypatch.setattr(main, 'run_query', run)
    assert client.post('/v1/query', headers=headers(second), json={'question': 'How many employees?', 'session_id': f'user:{first["user"]["id"]}'}).status_code == 200
    assert captured == [f'user:{second["user"]["id"]}']


def test_signin_rate_limit(account_db):
    client, _ = account_db
    for _ in range(10):
        assert client.post('/v1/auth/login', json={'email': 'brute@example.com', 'password': 'wrong'}).status_code == 401
    assert client.post('/v1/auth/login', json={'email': 'brute@example.com', 'password': 'wrong'}).status_code == 429


def test_google_signin_routes_are_removed(account_db):
    client, _ = account_db
    for path in ("start", "callback"):
        assert client.get("/v1/auth/google/" + path).status_code == 404
    assert client.post("/v1/auth/google/exchange", json={}).status_code == 404
