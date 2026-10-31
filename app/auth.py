"""Persistent opaque sessions. Passwords and tokens are never stored raw."""
import hashlib
import hmac
import re
import secrets
from threading import BoundedSemaphore
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError

from app.db import AuthAttempt, AuthSession, User, metadata_session

router = APIRouter(prefix='/v1/auth', tags=['accounts'])
bearer = HTTPBearer(auto_error=False)
password_capacity = BoundedSemaphore(4)


def now():
    return datetime.now(timezone.utc)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    with password_capacity:
        derived = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=5)
    return 'scrypt$16384$8$5$' + salt + '$' + derived.hex()


def password_matches(password, stored):
    if not stored:
        return False
    try:
        parts = stored.split('$')
        if len(parts) == 3 and parts[0] == 'scrypt':
            with password_capacity:
                legacy = hashlib.scrypt(password.encode(), salt=bytes.fromhex(parts[1]), n=16384, r=8, p=1)
                # Match current derivation effort even when the old password is wrong.
                hashlib.scrypt(password.encode(), salt=bytes.fromhex(parts[1]), n=16384, r=8, p=4)
            return hmac.compare_digest(legacy.hex(), parts[2])
        if len(parts) == 6 and parts[:4] == ['scrypt', '16384', '8', '5']:
            return hmac.compare_digest(password_hash(password, parts[4]), stored)
        return False
    except (ValueError, IndexError):
        return False


DUMMY_PASSWORD_HASH = password_hash('unused dummy value', '0' * 32)


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)

    @field_validator('email')
    @classmethod
    def email_format(cls, value):
        value = value.strip().lower()
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value):
            raise ValueError('Enter a valid email address.')
        return value


class Signup(Credentials):
    name: str = Field(min_length=1, max_length=80)

    @field_validator('name')
    @classmethod
    def name_format(cls, value):
        value = value.strip()
        if not value:
            raise ValueError('Enter your name.')
        return value

    @field_validator('password')
    @classmethod
    def password_length(cls, value):
        if len(value) < 10:
            raise ValueError('Use at least 10 characters for your password.')
        return value


def profile(user):
    return {'id': user.id, 'name': user.name, 'email': user.email,
            'provider': 'google' if user.google_id else 'email', 'created_at': user.created_at.isoformat()}


def issue_session(db, user):
    token = secrets.token_urlsafe(32)
    user.last_login = now()
    db.add(AuthSession(token_hash=digest(token), user_id=user.id, expires_at=now() + timedelta(days=7)))
    db.execute(delete(AuthSession).where(AuthSession.expires_at < now()))
    db.commit()
    return {'token': token, 'user': profile(user)}


def rate_limit(request, email=''):
    host = request.client.host if request.client else 'unknown'
    buckets = [(digest('ip:' + host), 80)]
    if email:
        buckets.append((digest('email:' + email), 10))
    with metadata_session() as db:
        if db.get_bind().dialect.name == 'postgresql':
            # Serialize counters across API workers; a count-then-insert race
            # must not let simultaneous login attempts bypass the limit.
            for bucket, _ in sorted(buckets):
                key = int.from_bytes(bytes.fromhex(bucket[:16]), 'big', signed=True)
                db.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': key})
        cutoff = now() - timedelta(minutes=10)
        db.execute(delete(AuthAttempt).where(AuthAttempt.timestamp < cutoff))
        for bucket, limit in buckets:
            count = db.scalar(select(func.count()).select_from(AuthAttempt).where(AuthAttempt.bucket == bucket))
            if count >= limit:
                raise HTTPException(429, 'Too many sign-in attempts. Try again in 10 minutes.')
        for bucket, _ in buckets:
            db.add(AuthAttempt(bucket=bucket, timestamp=now()))
        db.commit()


def require_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    if not credentials:
        raise HTTPException(401, 'Sign in to use your query studio.')
    with metadata_session() as db:
        login = db.scalar(select(AuthSession).where(AuthSession.token_hash == digest(credentials.credentials),
                                                    AuthSession.expires_at > now()))
        user = db.get(User, login.user_id) if login else None
        if not user:
            raise HTTPException(401, 'Your session has expired. Please sign in again.')
        return profile(user)


@router.post('/signup', status_code=201)
def signup(payload: Signup, request: Request):
    rate_limit(request, payload.email)
    with metadata_session() as db:
        user = User(name=payload.name, email=payload.email, password_hash=password_hash(payload.password))
        db.add(user)
        try:
            db.flush()
            return issue_session(db, user)
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, 'This email already has an account. Please sign in.')


@router.post('/login')
def login(payload: Credentials, request: Request):
    rate_limit(request, payload.email)
    with metadata_session() as db:
        user = db.scalar(select(User).where(User.email == payload.email))
        # Do an equivalent password derivation even for unknown addresses.
        candidate = user.password_hash if user and user.password_hash else DUMMY_PASSWORD_HASH
        valid = password_matches(payload.password, candidate)
        if not valid or not user or not user.password_hash:
            raise HTTPException(401, 'Email or password is incorrect.')
        if len(user.password_hash.split('$')) == 3:
            user.password_hash = password_hash(payload.password)
        return issue_session(db, user)


@router.get('/me')
def me(user=Depends(require_user)):
    return user


@router.post('/logout')
def logout(user=Depends(require_user), credentials=Depends(bearer)):
    with metadata_session() as db:
        db.execute(delete(AuthSession).where(AuthSession.token_hash == digest(credentials.credentials)))
        db.commit()
    return {'signed_out': True}
