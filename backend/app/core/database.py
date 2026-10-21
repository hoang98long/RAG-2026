from functools import lru_cache
from pathlib import Path
from typing import Literal
from fastapi import Query, Request
from app.core.access import require_private_access
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from app.core.config import get_settings

settings = get_settings()
engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@lru_cache
def public_session_factory():
    settings = get_settings()
    url = make_url(settings.public_database_url)
    Path(url.database).parent.mkdir(parents=True, exist_ok=True)
    public_engine = create_engine(url, pool_pre_ping=True)
    Base.metadata.create_all(bind=public_engine)
    return sessionmaker(bind=public_engine, autoflush=False, autocommit=False)


def get_scope_db(request: Request, scope: Literal['private', 'public'] = Query('private')):
    if scope == 'private':
        require_private_access(request)
        yield from get_db()
    else:
        with public_session_factory()() as public_db:
            yield public_db


def get_private_db(request: Request):
    require_private_access(request)
    yield from get_db()
