"""Fixtures for the Grad Café test suite.

Database
--------
Every database test runs against a throwaway PostgreSQL database named by
``TEST_DATABASE_URL`` (default ``postgresql://localhost/gradcafe_test``).  The
fixture exports that value as ``DATABASE_URL`` for the duration of the session,
so application defaults resolve to the test database and a developer's real
``DATABASE_URL`` is never touched.

Test doubles
------------
``make_app`` builds the Flask application through :func:`src.flask_app.create_app`
with injected fakes.  ``client`` is wired to the real test database with a fake
scraper; ``stub_client`` replaces every service, so page tests need no database.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List

import psycopg
import pytest

from src import flask_app, load_data, query_data
from helpers import Recorder, raw_records

DEFAULT_TEST_DATABASE_URL = "postgresql://localhost/gradcafe_test"


@pytest.fixture(scope="session")
def database_url() -> str:
    """Return the connection string for the throwaway test database."""
    url = os.environ.get("TEST_DATABASE_URL") or DEFAULT_TEST_DATABASE_URL
    try:
        psycopg.connect(url).close()
    except psycopg.OperationalError as exc:  # pragma: no cover - environment guard
        pytest.exit(
            f"Cannot reach the test database at {url}: {exc}\n"
            "Create it with `createdb gradcafe_test` or set TEST_DATABASE_URL.",
            returncode=1,
        )
    return url


@pytest.fixture(autouse=True)
def _database_env(monkeypatch: pytest.MonkeyPatch, database_url: str) -> None:
    """Point every ``DATABASE_URL`` default at the test database."""
    monkeypatch.setenv("DATABASE_URL", database_url)


@pytest.fixture
def conn(database_url: str):
    """An open connection to an empty ``applicants`` table."""
    connection = psycopg.connect(database_url)
    load_data.reset_schema(connection)
    try:
        yield connection
    finally:
        connection.close()


@pytest.fixture
def empty_db(conn) -> None:
    """Guarantee the target table exists and is empty before a test runs."""
    assert query_data.count_rows(conn=conn) == 0


@pytest.fixture
def records() -> List[Dict[str, Any]]:
    """Four raw scraped records with distinct result URLs."""
    return raw_records()


@pytest.fixture
def fake_scraper(records) -> Recorder:
    """A scraper double returning :func:`tests.helpers.raw_records`."""
    return Recorder(result=records)


@pytest.fixture
def make_app(database_url: str):
    """Factory building an application through the real ``create_app`` factory.

    Keyword arguments are forwarded to :func:`src.flask_app.create_app`, so a
    test can swap any single service and keep the real implementation of the
    rest.
    """

    def factory(**overrides: Any) -> flask_app.Flask:
        config = {"TESTING": True, "DATABASE_URL": database_url}
        config.update(overrides.pop("config", {}))
        return flask_app.create_app(config=config, **overrides)

    return factory


@pytest.fixture
def app(make_app, fake_scraper, conn):
    """Application wired to the real test database with a fake scraper.

    The ``conn`` dependency resets the schema first, so each test starts from an
    empty ``applicants`` table.
    """
    application = make_app(scraper=fake_scraper)
    application.extensions[flask_app.EXTENSION_KEY]["fake_scraper"] = fake_scraper
    return application


@pytest.fixture
def client(app):
    """Flask test client for the database-backed application."""
    return app.test_client()


@pytest.fixture
def state(app) -> flask_app.PullState:
    """The :class:`src.flask_app.PullState` of the database-backed application."""
    return app.extensions[flask_app.EXTENSION_KEY]["state"]


@pytest.fixture
def stub_services(records) -> Dict[str, Recorder]:
    """Doubles for every injected service, so no database is required."""
    analysis = {spec.key: 1.0 for spec in query_data.ANALYSIS_SPECS}
    analysis["percent_international"] = 39.284
    return {
        "scraper": Recorder(result=records),
        "loader": Recorder(result=len(records)),
        "analysis_provider": Recorder(result=analysis),
        "rows_provider": Recorder(result=[]),
    }


@pytest.fixture
def stub_app(make_app, stub_services):
    """Fully stubbed application: no database, no network."""
    return make_app(**stub_services)


@pytest.fixture
def stub_client(stub_app):
    """Flask test client for the fully stubbed application."""
    return stub_app.test_client()
