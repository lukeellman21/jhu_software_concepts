"""Database connection helpers.

Every module reads the connection string from the ``DATABASE_URL`` environment
variable so that the application, the test suite and CI can each point at a
different PostgreSQL instance without code changes.
"""
from __future__ import annotations

import os
from typing import Any, Optional

import psycopg

#: Used when ``DATABASE_URL`` is not set in the environment.
DEFAULT_DATABASE_URL = "postgresql://localhost/gradcafe"


def get_database_url(database_url: Optional[str] = None) -> str:
    """Return the PostgreSQL connection string to use.

    :param database_url: explicit override; when ``None`` the ``DATABASE_URL``
        environment variable is used, falling back to
        :data:`DEFAULT_DATABASE_URL`.
    :returns: a libpq connection string.
    """
    if database_url:
        return database_url
    return os.environ.get("DATABASE_URL") or DEFAULT_DATABASE_URL


def sqlalchemy_url(database_url: Optional[str] = None) -> str:
    """Return :func:`get_database_url` rewritten for the SQLAlchemy psycopg driver.

    ``postgresql://host/db`` becomes ``postgresql+psycopg://host/db`` so that
    SQLAlchemy uses psycopg 3 rather than the (unavailable) psycopg2 default.
    """
    url = get_database_url(database_url)
    if url.startswith("postgresql+"):
        return url
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url.replace("postgres://", "postgresql+psycopg://", 1)


def connect(database_url: Optional[str] = None, **kwargs: Any) -> psycopg.Connection:
    """Open a new psycopg connection.

    :param database_url: optional connection-string override.
    :param kwargs: forwarded to :func:`psycopg.connect`.
    """
    return psycopg.connect(get_database_url(database_url), **kwargs)
