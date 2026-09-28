"""SQLAlchemy ORM mapping for the ``applicants`` table.

The engine is created lazily by :func:`get_engine` so that the connection
string is read when a session is first requested rather than at import time --
that is what lets the test suite point the ORM at a throwaway database.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy import Column, Date, Float, Integer, Text, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from . import db

Base = declarative_base()


class Applicant(Base):
    """One Grad Café entry; mirrors :data:`src.load_data.CREATE_TABLE_SQL`."""

    __tablename__ = "applicants"

    p_id = Column(Integer, primary_key=True)
    program = Column(Text, nullable=False)
    comments = Column(Text, nullable=False)
    date_added = Column(Date, nullable=True)
    url = Column(Text, nullable=False)
    status = Column(Text, nullable=False)
    term = Column(Text, nullable=False)
    us_or_international = Column(Text, nullable=False)
    gpa = Column(Float, nullable=True)
    gre = Column(Float, nullable=True)
    gre_v = Column(Float, nullable=True)
    gre_aw = Column(Float, nullable=True)
    degree = Column(Text, nullable=False)
    llm_generated_program = Column(Text, nullable=True)
    llm_generated_university = Column(Text, nullable=True)

    def to_dict(self) -> Dict[str, Any]:
        """Return the row as a plain dict keyed by column name."""
        return {column.name: getattr(self, column.name) for column in self.__table__.columns}


_ENGINES: Dict[str, Engine] = {}


def get_engine(database_url: Optional[str] = None, **kwargs: Any) -> Engine:
    """Return (and cache) the SQLAlchemy engine for a connection string."""
    url = db.sqlalchemy_url(database_url)
    if url not in _ENGINES:
        _ENGINES[url] = create_engine(url, echo=False, future=True, **kwargs)
    return _ENGINES[url]


def get_session_factory(database_url: Optional[str] = None) -> sessionmaker:
    """Return a :class:`sqlalchemy.orm.sessionmaker` bound to the engine."""
    return sessionmaker(bind=get_engine(database_url), future=True)


def get_db_session(database_url: Optional[str] = None) -> Session:
    """Open a new ORM session against ``DATABASE_URL`` (or the override)."""
    return get_session_factory(database_url)()
