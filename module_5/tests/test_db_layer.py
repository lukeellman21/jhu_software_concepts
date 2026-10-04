"""Connection helpers, the ORM mapping and the ORM report.

Marker: ``db``.
"""
from __future__ import annotations

import psycopg
import pytest
from sqlalchemy.orm import Session

from src import db, load_data, models, orm_queries

pytestmark = pytest.mark.db


class TestConnectionSettings:
    """``DATABASE_URL`` resolution and driver-specific rewriting."""

    def test_explicit_url_wins(self):
        assert db.get_database_url("postgresql://localhost/explicit") == (
            "postgresql://localhost/explicit"
        )

    def test_environment_variable_is_used(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/from_env")
        assert db.get_database_url() == "postgresql://localhost/from_env"

    def test_default_is_used_when_unset(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        assert db.get_database_url() == db.DEFAULT_DATABASE_URL

    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("postgresql://localhost/gradcafe", "postgresql+psycopg://localhost/gradcafe"),
            ("postgres://localhost/gradcafe", "postgresql+psycopg://localhost/gradcafe"),
            (
                "postgresql+psycopg://localhost/gradcafe",
                "postgresql+psycopg://localhost/gradcafe",
            ),
        ],
    )
    def test_sqlalchemy_url_selects_the_psycopg_driver(self, raw, expected):
        assert db.sqlalchemy_url(raw) == expected

    def test_connect_returns_an_open_connection(self, database_url):
        connection = db.connect(database_url)
        try:
            assert isinstance(connection, psycopg.Connection)
            assert connection.execute("SELECT 1").fetchone()[0] == 1
        finally:
            connection.close()


class TestOrmMapping:
    """The SQLAlchemy model and its lazily built engine."""

    def test_engine_is_cached_per_url(self, database_url):
        first = models.get_engine(database_url)
        second = models.get_engine(database_url)
        assert first is second

    def test_session_factory_is_bound_to_the_engine(self, database_url):
        factory = models.get_session_factory(database_url)
        session = factory()
        try:
            assert session.get_bind() is models.get_engine(database_url)
        finally:
            session.close()

    def test_get_db_session_returns_a_session(self, database_url):
        session = models.get_db_session(database_url)
        try:
            assert isinstance(session, Session)
        finally:
            session.close()

    def test_model_round_trips_through_to_dict(self, conn, database_url, records):
        load_data.insert_rows(records, conn=conn)
        session = models.get_db_session(database_url)
        try:
            applicant = session.get(models.Applicant, 1000001)
            row = applicant.to_dict()
        finally:
            session.close()

        assert set(row) == set(load_data.COLUMNS)
        assert row["program"].startswith("Johns Hopkins University")
        assert row["status"] == "Accepted"


class TestOrmReport:
    """The Module-3 ORM report."""

    def test_percent_guards_against_an_empty_denominator(self):
        assert orm_queries._percent(0, 0) == 0.0
        assert orm_queries._percent(1, 4) == 25.0

    def test_report_answers_match_the_loaded_rows(self, conn, database_url, records):
        load_data.insert_rows(records, conn=conn)

        results = orm_queries.run_orm_queries(database_url=database_url, verbose=False)

        assert results["fall_2026_count"] == 2
        assert results["avg_gpa_american_fall_2026"] == pytest.approx(3.95, abs=0.01)
        assert results["fall_2025_acceptance_percent"] == pytest.approx(0.0)
        # The fixture holds a JHU and a Stanford PhD CS acceptance; only
        # Stanford is one of the universities questions 8 and 9 ask about.
        assert results["fall_2026_phd_cs_acceptances"] == 1
        assert results["llm_fall_2026_phd_cs_acceptances"] == 1
        assert results["acceptance_percent_high_gpa"] == pytest.approx(100.0)

    def test_report_prints_formatted_answers(self, conn, database_url, records, capsys):
        load_data.insert_rows(records, conn=conn)
        session = models.get_db_session(database_url)
        try:
            orm_queries.run_orm_queries(session=session)
        finally:
            session.close()

        out = capsys.readouterr().out
        assert "ORM Fall 2026 applicant count: 2" in out
        assert "ORM Fall 2025 acceptance percentage: 0.00%" in out
        assert "ORM acceptance percentage, GPA >= 3.80: 100.00%" in out

    def test_report_on_an_empty_database_is_all_zeroes(self, conn, database_url):
        results = orm_queries.run_orm_queries(database_url=database_url, verbose=False)

        assert results["fall_2026_count"] == 0
        assert results["avg_gpa_american_fall_2026"] is None
        assert results["acceptance_percent_high_gpa"] == 0.0
