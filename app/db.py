from datetime import datetime, timezone
from functools import lru_cache
from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from app.config import settings


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = 'studio_users'
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    google_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuthSession(Base):
    __tablename__ = 'studio_sessions'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('studio_users.id'), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class GoogleFlow(Base):
    __tablename__ = 'studio_google_flows'
    state_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    nonce: Mapped[str] = mapped_column(String(100))
    verifier: Mapped[str] = mapped_column(String(100))
    browser_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class LoginTicket(Base):
    __tablename__ = 'studio_login_tickets'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('studio_users.id'))
    browser_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AuthAttempt(Base):
    __tablename__ = 'studio_auth_attempts'
    id: Mapped[int] = mapped_column(primary_key=True)
    bucket: Mapped[str] = mapped_column(String(64), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class History(Base):
    __tablename__ = 'query_history'
    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    session_id: Mapped[str] = mapped_column(String(100))
    question: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40))
    response: Mapped[dict] = mapped_column(JSON)


class Feedback(Base):
    __tablename__ = 'feedback'
    id: Mapped[int] = mapped_column(primary_key=True)
    query_id: Mapped[int] = mapped_column(ForeignKey('query_history.id'))
    correct: Mapped[bool] = mapped_column(Boolean)
    comment: Mapped[str] = mapped_column(Text)


@lru_cache
def demo_engine():
    if not settings().readonly_database_url:
        raise RuntimeError('READONLY_DATABASE_URL is not configured')
    return create_engine(settings().readonly_database_url, pool_pre_ping=True, connect_args={'connect_timeout': 5})


def analytical_engine():
    from app.sources import current_source
    source = current_source.get()
    return source['engine'] if source else demo_engine()


class Dataset(Base):
    __tablename__ = 'studio_datasets'
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('studio_users.id'), index=True)
    name: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(20))
    size_bytes: Mapped[int] = mapped_column()
    tables: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


@lru_cache
def metadata_engine():
    if not settings().database_url:
        raise RuntimeError('DATABASE_URL is not configured')
    return create_engine(settings().database_url, pool_pre_ping=True, connect_args={'connect_timeout': 5})


def metadata_session():
    return sessionmaker(metadata_engine())()


def save_history(request, response):
    with metadata_session() as session:
        record = History(session_id=request.session_id, question=request.question,
                         status=response.status, response=response.model_dump(mode='json'))
        session.add(record)
        session.flush()
        response.id = record.id
        record.response = response.model_dump(mode='json')
        session.commit()
