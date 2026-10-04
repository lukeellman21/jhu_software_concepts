"""Database connection helpers.

Connection settings come from the environment, never from source.  Two forms
are supported, in this order of precedence:

1. the discrete variables ``DB_HOST``, ``DB_PORT``, ``DB_NAME``, ``DB_USER``
   and ``DB_PASSWORD`` (see ``.env.example``), which is how the application is
   configured in deployment and in CI;
2. a single ``DATABASE_URL`` libpq connection string, which is convenient for
   local development and for the test suite.

Nothing in this module logs or echoes a password.
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

import psycopg

#: Used when neither the discrete variables nor ``DATABASE_URL`` are set.
DEFAULT_DATABASE_URL = "postgresql://localhost/gradcafe"

#: Environment variable names for the discrete connection settings.
DB_ENV_VARS = ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD")

#: Maps the environment variable names onto libpq connection keywords.
_LIBPQ_KEYS = {
    "DB_HOST": "host",
    "DB_PORT": "port",
    "DB_NAME": "dbname",
    "DB_USER": "user",
    "DB_PASSWORD": "password",
}


def get_connection_settings() -> Optional[Dict[str, str]]:
    """Return libpq keyword settings built from the discrete ``DB_*`` variables.

    :returns: a mapping of libpq keywords to values, or ``None`` when none of
        the ``DB_*`` variables are set (in which case the caller falls back to
        ``DATABASE_URL``).
    """
    settings = {
        _LIBPQ_KEYS[name]: os.environ[name]
        for name in DB_ENV_VARS
        if os.environ.get(name)
    }
    return settings or None


def get_database_url(database_url: Optional[str] = None) -> str:
    """Return the ``DATABASE_URL`` connection string to use.

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

    :param database_url: optional connection-string override.
    :returns: a SQLAlchemy connection URL.
    """
    url = get_database_url(database_url)
    if url.startswith("postgresql+"):
        return url
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url.replace("postgres://", "postgresql+psycopg://", 1)


def describe_connection(database_url: Optional[str] = None) -> str:
    """Return a human-readable connection description with no password in it.

    :param database_url: optional connection-string override.
    :returns: ``"host:port/dbname as user"`` when the discrete variables are in
        use, otherwise the ``DATABASE_URL`` with any password redacted.
    """
    settings = None if database_url else get_connection_settings()
    if settings:
        return (
            f"{settings.get('host', 'localhost')}:{settings.get('port', '5432')}"
            f"/{settings.get('dbname', '?')} as {settings.get('user', '?')}"
        )
    url = get_database_url(database_url)
    if "@" in url:
        scheme, _, rest = url.partition("://")
        return f"{scheme}://***@{rest.rpartition('@')[2]}"
    return url


def connect(database_url: Optional[str] = None, **kwargs: Any) -> psycopg.Connection:
    """Open a new psycopg connection.

    Uses the discrete ``DB_*`` variables when they are set and no explicit
    override is given; otherwise connects with the ``DATABASE_URL`` string.

    :param database_url: optional connection-string override.
    :param kwargs: forwarded to :func:`psycopg.connect`.
    :returns: an open connection.
    """
    settings = None if database_url else get_connection_settings()
    if settings:
        return psycopg.connect(**settings, **kwargs)
    return psycopg.connect(get_database_url(database_url), **kwargs)
