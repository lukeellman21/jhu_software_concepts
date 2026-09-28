"""Database schema, inserts, idempotency and the query function.

Marker: ``db``.  These tests run against a real PostgreSQL database (see
``tests/conftest.py``) because the uniqueness policy and the ``NOT NULL``
constraints are enforced by the database, not by Python.
"""
from __future__ import annotations

import json

import psycopg
import pytest

from src import load_data, query_data

pytestmark = pytest.mark.db


def column_metadata(conn):
    """Return ``{column_name: is_nullable}`` for the ``applicants`` table."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'applicants'
            """
        )
        return {name: nullable == "YES" for name, nullable in cur.fetchall()}


def test_schema_matches_the_module_3_columns(conn):
    """The table exposes exactly the Module-3 column set."""
    assert set(column_metadata(conn)) == set(load_data.COLUMNS)


def test_required_fields_are_not_nullable(conn):
    """The required fields are enforced by the database, not just by the loader."""
    nullable = column_metadata(conn)
    for field in load_data.REQUIRED_FIELDS:
        assert nullable[field] is False, f"{field} should be NOT NULL"


def test_target_table_is_empty_before_a_pull(empty_db, conn):
    """The pull tests start from an empty table."""
    assert query_data.count_rows(conn=conn) == 0


def test_pull_inserts_rows_with_required_non_null_fields(client, conn, records, empty_db):
    """After ``POST /pull-data`` the scraped rows are in PostgreSQL, fully populated."""
    response = client.post("/pull-data")

    assert response.status_code == 200
    assert response.get_json()["rows_loaded"] == len(records)

    columns = ", ".join(load_data.REQUIRED_FIELDS)
    with conn.cursor() as cur:
        cur.execute(f"SELECT {columns} FROM applicants;")
        rows = cur.fetchall()

    assert len(rows) == len(records)
    for row in rows:
        assert all(value is not None for value in row)


def test_pull_derives_the_primary_key_from_the_result_url(client, conn, empty_db):
    """``p_id`` comes from the Grad Café result id, which is what makes pulls idempotent."""
    client.post("/pull-data")

    with conn.cursor() as cur:
        cur.execute("SELECT p_id, url FROM applicants ORDER BY p_id;")
        rows = cur.fetchall()

    assert [p_id for p_id, _ in rows] == [1000001, 1000002, 1000003, 1000004]
    for p_id, url in rows:
        assert url.endswith(str(p_id))


def test_a_duplicate_pull_does_not_duplicate_rows(client, conn, records, empty_db):
    """Pulling the same data twice leaves the row count unchanged."""
    first = client.post("/pull-data").get_json()
    second = client.post("/pull-data").get_json()

    assert first["rows_loaded"] == len(records)
    assert second["rows_loaded"] == 0
    assert query_data.count_rows(conn=conn) == len(records)


def test_insert_rows_is_idempotent(conn, records):
    """The loader itself is idempotent, independent of the web layer."""
    assert load_data.insert_rows(records, conn=conn) == len(records)
    assert load_data.insert_rows(records, conn=conn) == 0
    assert query_data.count_rows(conn=conn) == len(records)


def test_insert_rows_opens_its_own_connection(database_url, conn, records):
    """Called without a connection, the loader opens one from ``DATABASE_URL``."""
    inserted = load_data.insert_rows(records, database_url=database_url)

    assert inserted == len(records)
    assert query_data.count_rows(conn=conn) == len(records)


def test_insert_rows_accepts_pre_normalised_rows(conn, records):
    """``normalize=False`` inserts rows that were normalised earlier."""
    rows = load_data.normalize_records(records)

    assert load_data.insert_rows(rows, conn=conn, normalize=False) == len(records)


def test_a_failing_batch_writes_nothing(conn, records):
    """A constraint violation rolls the whole batch back -- no partial writes."""
    rows = load_data.normalize_records(records)
    rows[-1]["program"] = None

    with pytest.raises(psycopg.errors.NotNullViolation):
        load_data.insert_rows(rows, conn=conn, normalize=False)

    assert query_data.count_rows(conn=conn) == 0


def test_ensure_schema_is_safe_to_repeat(conn, records):
    """``ensure_schema`` creates the table once and never drops existing rows."""
    load_data.insert_rows(records, conn=conn)
    load_data.ensure_schema(conn)

    assert query_data.count_rows(conn=conn) == len(records)


def test_reset_schema_clears_existing_rows(conn, records):
    """``reset_schema`` drops and recreates the table."""
    load_data.insert_rows(records, conn=conn)
    load_data.reset_schema(conn)

    assert query_data.count_rows(conn=conn) == 0


def test_query_function_returns_the_keys_the_template_uses(conn, records):
    """``get_analysis`` answers with a dict keyed by every expected key."""
    load_data.insert_rows(records, conn=conn)

    analysis = query_data.get_analysis(conn=conn)

    assert set(analysis) == set(query_data.EXPECTED_KEYS)
    assert analysis["total_applicants"] == len(records)
    assert analysis["fall_2026_count"] == 2
    assert analysis["avg_gpa"] == pytest.approx(3.75, abs=0.01)


def test_get_analysis_opens_its_own_connection(database_url, conn, records):
    """``get_analysis`` works without being handed a connection."""
    load_data.insert_rows(records, conn=conn)

    analysis = query_data.get_analysis(database_url=database_url)

    assert analysis["total_applicants"] == len(records)


def test_get_analysis_of_an_empty_table_returns_neutral_values(conn):
    """With no rows, counts are zero and averages are ``None``."""
    analysis = query_data.get_analysis(conn=conn)

    assert analysis["total_applicants"] == 0
    assert analysis["avg_gpa"] is None
    assert analysis["percent_international"] is None


def test_get_recent_rows_returns_dicts_with_every_column(conn, records):
    """The row query returns dicts keyed by the Module-3 fields."""
    load_data.insert_rows(records, conn=conn)

    rows = query_data.get_recent_rows(limit=2, conn=conn)

    assert len(rows) == 2
    assert set(rows[0]) == set(query_data.ROW_KEYS)
    assert rows[0]["p_id"] > rows[1]["p_id"]


def test_get_recent_rows_and_count_rows_open_their_own_connections(database_url, conn, records):
    """Both query helpers can connect for themselves."""
    load_data.insert_rows(records, conn=conn)

    assert len(query_data.get_recent_rows(limit=10, database_url=database_url)) == len(records)
    assert query_data.count_rows(database_url=database_url) == len(records)


def test_load_data_reads_the_bundled_sample_file(conn):
    """``load_data`` loads the repository's sample dataset without touching the network."""
    inserted = load_data.load_data(reset=True)

    assert inserted > 0
    assert query_data.count_rows(conn=conn) == inserted


def test_load_data_accepts_an_explicit_file(conn, records, tmp_path):
    """A dataset path can be passed explicitly."""
    dataset = tmp_path / "records.json"
    dataset.write_text(json.dumps(records), encoding="utf-8")

    assert load_data.load_data(path=str(dataset)) == len(records)


def test_read_records_honours_the_data_file_environment_variable(monkeypatch, records, tmp_path):
    """``GRADCAFE_DATA_FILE`` overrides the bundled default."""
    dataset = tmp_path / "records.json"
    dataset.write_text(json.dumps(records), encoding="utf-8")
    monkeypatch.setenv("GRADCAFE_DATA_FILE", str(dataset))

    assert load_data.read_records() == records


def test_read_records_defaults_to_the_bundled_dataset(monkeypatch):
    """Without an override the bundled sample dataset is used."""
    monkeypatch.delenv("GRADCAFE_DATA_FILE", raising=False)

    assert len(load_data.read_records()) > 0


def test_loader_cli_loads_and_reports(conn, capsys):
    """``python -m src.load_data --reset`` loads the sample data and says how many."""
    inserted = load_data.main(["--reset"])
    out = capsys.readouterr().out

    assert inserted > 0
    assert f"Inserted {inserted} new row(s)" in out
    assert query_data.count_rows(conn=conn) == inserted
