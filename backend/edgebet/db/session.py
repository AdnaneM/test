"""Moteur et sessions SQLAlchemy."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from edgebet.db.models import Base

_engines: dict[str, Engine] = {}


def get_engine(url: str) -> Engine:
    if url not in _engines:
        kwargs = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {}
        _engines[url] = create_engine(url, future=True, **kwargs)
    return _engines[url]


def init_db(url: str) -> Engine:
    engine = get_engine(url)
    Base.metadata.create_all(engine)
    return engine


@contextmanager
def session_scope(url: str) -> Iterator[Session]:
    engine = init_db(url)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
