"""SQL injection defenses, LIMIT enforcement and credential handling.

Marker: ``db``.  These tests exercise the Module 5 hardening work: composed
statements, parameter binding, the identifier allow-list, the limit clamp and
environment-driven connection settings.
"""
from __future__ import annotations

import psycopg
import pytest
from psycopg import conninfo, sql

from src import db, load_data, query_data

pytestmark = pytest.mark.db

#: Obvious placeholder used where a test needs a password-shaped value.
#: Named so that neither a reader nor a secret scanner mistakes it for a real one.
PLACEHOLDER_SECRET = "example-not-a-real-password"

#: Inputs a hostile client might send.
INJECTION_PAYLOADS = (
    "'; DROP TABLE applicants; --",
    "' OR '1'='1",
    "' UNION SELECT p_id, url FROM applicants --",
    "%",
    "_",
    "\\",
)


def statement_text(statement, conn) -> str:
    """Render a composed statement to the SQL text psycopg will send."""
    return statement.as_string(conn)


class TestLimitClamp:
    """Every query is capped, and the cap cannot be argued with."""

    @pytest.mark.parametrize(
        "requested, expected",
        [
            (10, 10),
            ("25", 25),
            (" 7 ", 7),
            (0, query_data.MIN_LIMIT),
            (-5, query_data.MIN_LIMIT),
            (101, query_data.MAX_LIMIT),
            (10**9, query_data.MAX_LIMIT),
            (None, query_data.DEFAULT_LIMIT),
            ("", query_data.DEFAULT_LIMIT),
            ("abc", query_data.DEFAULT_LIMIT),
            ("10; DROP TABLE applicants", query_data.DEFAULT_LIMIT),
            (3.5, query_data.DEFAULT_LIMIT),
        ],
    )
    def test_clamp_limit(self, requested, expected):
        assert query_data.clamp_limit(requested) == expected

    def test_clamp_limit_honours_a_custom_default(self):
        assert query_data.clamp_limit("nonsense", default=5) == 5

    def test_clamped_limit_is_always_in_range(self):
        for payload in INJECTION_PAYLOADS:
            limit = query_data.clamp_limit(payload)
            assert query_data.MIN_LIMIT <= limit <= query_data.MAX_LIMIT

    def test_an_oversized_request_cannot_widen_a_query(self, conn, records):
        """Asking for a million rows returns at most MAX_LIMIT."""
        load_data.insert_rows(records, conn=conn)

        rows = query_data.get_recent_rows(limit=10**9, conn=conn)

        assert len(rows) <= query_data.MAX_LIMIT


class TestComposedStatements:
    """Statements are composed objects, built separately from their values."""

    def test_statements_are_composed_not_strings(self):
        """No spec carries raw SQL text that could be concatenated."""
        for spec in query_data.ANALYSIS_SPECS:
            assert isinstance(spec.statement, sql.Composable)
            assert not isinstance(spec.statement, str)

    def test_every_analysis_statement_has_a_limit(self, conn):
        for spec in query_data.ANALYSIS_SPECS:
            assert "LIMIT" in statement_text(spec.statement, conn)

    def test_the_rows_statement_has_a_limit(self, conn):
        statement, _ = query_data.build_rows_statement()
        assert statement_text(statement, conn).rstrip().endswith("LIMIT %s")

    def test_identifiers_are_quoted(self, conn):
        """Column and table names are rendered as quoted identifiers."""
        statement, _ = query_data.build_rows_statement()
        text = statement_text(statement, conn)

        assert '"applicants"' in text
        assert '"p_id"' in text

    def test_the_insert_statement_is_composed(self, conn):
        text = statement_text(load_data.INSERT_ROW_SQL, conn)

        assert text.startswith('INSERT INTO "applicants"')
        assert "ON CONFLICT" in text
        for column in load_data.COLUMNS:
            assert f'"{column}"' in text
            assert f"%({column})s" in text


class TestSortColumnAllowList:
    """The only dynamic identifier is a sort column, and it is allow-listed."""

    @pytest.mark.parametrize("payload", INJECTION_PAYLOADS)
    def test_a_malicious_sort_column_falls_back_to_the_default(self, payload, conn):
        statement, _ = query_data.build_rows_statement(sort_by=payload)
        text = statement_text(statement, conn)

        assert 'ORDER BY "p_id"' in text
        assert "DROP" not in text.upper()

    @pytest.mark.parametrize("column", query_data.ROW_KEYS)
    def test_every_allow_listed_column_is_accepted(self, column, conn):
        statement, _ = query_data.build_rows_statement(sort_by=column)
        assert f'ORDER BY "{column}"' in statement_text(statement, conn)

    def test_sort_direction_is_not_user_text(self, conn):
        ascending, _ = query_data.build_rows_statement(descending=False)
        descending, _ = query_data.build_rows_statement(descending=True)

        assert statement_text(ascending, conn).endswith("ASC LIMIT %s")
        assert statement_text(descending, conn).endswith("DESC LIMIT %s")


class TestSearchParameterisation:
    """Search terms are bound as values, never spliced into SQL text."""

    def test_the_sql_text_is_identical_whatever_the_user_sends(self, conn):
        """The strongest statement of the defense: input changes params, not SQL."""
        baseline = statement_text(
            query_data.build_rows_statement(search="harmless")[0], conn
        )

        for payload in INJECTION_PAYLOADS:
            statement, params = query_data.build_rows_statement(search=payload)

            assert statement_text(statement, conn) == baseline
            assert len(params) == len(query_data.SEARCHABLE_COLUMNS)

    @pytest.mark.parametrize("payload", INJECTION_PAYLOADS)
    def test_no_payload_keyword_survives_into_the_sql(self, payload, conn):
        statement, _ = query_data.build_rows_statement(search=payload)
        text = statement_text(statement, conn).upper()

        for keyword in ("DROP", "UNION", "DELETE", "--", ";"):
            assert keyword not in text
        assert text.count("%S") == len(query_data.SEARCHABLE_COLUMNS) + 1

    @pytest.mark.parametrize("payload", ("%", "_"))
    def test_like_wildcards_are_matched_literally(self, payload, conn, records):
        """A bare wildcard must not act as "return everything"."""
        load_data.insert_rows(records, conn=conn)

        rows = query_data.get_recent_rows(search=payload, conn=conn)

        assert rows == []

    @pytest.mark.parametrize("payload", INJECTION_PAYLOADS)
    def test_the_table_survives_a_hostile_search(self, payload, conn, records):
        """A malicious search returns no data and leaves the table intact."""
        load_data.insert_rows(records, conn=conn)

        rows = query_data.get_recent_rows(search=payload, conn=conn)

        assert isinstance(rows, list)
        assert query_data.count_rows(conn=conn) == len(records)

    def test_a_tautology_does_not_return_everything(self, conn, records):
        """``' OR '1'='1`` is matched literally, so it finds nothing."""
        load_data.insert_rows(records, conn=conn)

        rows = query_data.get_recent_rows(search="' OR '1'='1", conn=conn)

        assert rows == []

    def test_a_legitimate_search_still_works(self, conn, records):
        load_data.insert_rows(records, conn=conn)

        rows = query_data.get_recent_rows(search="Computer Science", conn=conn)

        assert rows
        assert all("Computer Science" in row["program"] for row in rows)

    def test_an_empty_search_is_ignored(self, conn, records):
        load_data.insert_rows(records, conn=conn)

        assert len(query_data.get_recent_rows(search="   ", conn=conn)) == len(records)

    def test_rows_can_be_sorted_ascending(self, conn, records):
        load_data.insert_rows(records, conn=conn)

        rows = query_data.get_recent_rows(sort_by="p_id", descending=False, conn=conn)

        assert [row["p_id"] for row in rows] == sorted(row["p_id"] for row in rows)

    def test_get_recent_rows_opens_its_own_connection(self, database_url, conn, records):
        load_data.insert_rows(records, conn=conn)

        rows = query_data.get_recent_rows(
            limit=2, sort_by="gpa", descending=False, search=None,
            database_url=database_url,
        )

        assert len(rows) == 2


class TestEndpointHardening:
    """The HTTP surface refuses to be talked into anything."""

    @pytest.mark.parametrize("payload", INJECTION_PAYLOADS)
    def test_a_hostile_query_string_is_handled_safely(self, client, conn, records, payload):
        load_data.insert_rows(records, conn=conn)

        response = client.get(
            "/analysis", query_string={"q": payload, "sort": payload, "limit": payload}
        )

        assert response.status_code == 200
        assert query_data.count_rows(conn=conn) == len(records)

    def test_an_oversized_limit_is_clamped_by_the_endpoint(self, client, conn, records):
        load_data.insert_rows(records, conn=conn)

        response = client.get("/analysis", query_string={"limit": "100000"})
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        # The form echoes the clamped value, not what was asked for.
        assert f'value="{query_data.MAX_LIMIT}"' in body
        assert 'value="100000"' not in body

    def test_valid_options_are_echoed_back_into_the_form(self, client, conn, records):
        load_data.insert_rows(records, conn=conn)

        response = client.get(
            "/analysis", query_string={"q": "Stanford", "sort": "gpa", "limit": "5", "dir": "asc"}
        )
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        assert 'value="Stanford"' in body
        assert 'value="5"' in body


class TestConnectionSettings:
    """Credentials come from the environment, and never appear in logs."""

    def test_discrete_variables_are_read(self, monkeypatch):
        for name in db.DB_ENV_VARS:
            monkeypatch.delenv(name, raising=False)
        monkeypatch.setenv("DB_HOST", "db.example.com")
        monkeypatch.setenv("DB_PORT", "6543")
        monkeypatch.setenv("DB_NAME", "gradcafe")
        monkeypatch.setenv("DB_USER", "gradcafe_app")
        monkeypatch.setenv("DB_PASSWORD", PLACEHOLDER_SECRET)

        settings = db.get_connection_settings()

        # Asserted without a literal under a "password" key, which static
        # analysers flag as a hard-coded credential regardless of the value.
        assert {k: v for k, v in settings.items() if k != "password"} == {
            "host": "db.example.com",
            "port": "6543",
            "dbname": "gradcafe",
            "user": "gradcafe_app",
        }
        assert settings["password"] == PLACEHOLDER_SECRET

    def test_no_discrete_variables_means_none(self, monkeypatch):
        for name in db.DB_ENV_VARS:
            monkeypatch.delenv(name, raising=False)

        assert db.get_connection_settings() is None

    def test_describe_connection_hides_the_password(self, monkeypatch):
        for name in db.DB_ENV_VARS:
            monkeypatch.delenv(name, raising=False)
        monkeypatch.setenv("DB_HOST", "db.example.com")
        monkeypatch.setenv("DB_PORT", "6543")
        monkeypatch.setenv("DB_NAME", "gradcafe")
        monkeypatch.setenv("DB_USER", "gradcafe_app")
        monkeypatch.setenv("DB_PASSWORD", PLACEHOLDER_SECRET)

        description = db.describe_connection()

        assert description == "db.example.com:6543/gradcafe as gradcafe_app"
        assert PLACEHOLDER_SECRET not in description

    def test_describe_connection_redacts_a_url_password(self, monkeypatch):
        for name in db.DB_ENV_VARS:
            monkeypatch.delenv(name, raising=False)
        monkeypatch.setenv("DATABASE_URL", "postgresql://bob:hunter2@localhost/gradcafe")

        description = db.describe_connection()

        assert "hunter2" not in description
        assert "***" in description

    def test_describe_connection_of_a_plain_url(self, monkeypatch):
        for name in db.DB_ENV_VARS:
            monkeypatch.delenv(name, raising=False)

        assert db.describe_connection("postgresql://localhost/gradcafe") == (
            "postgresql://localhost/gradcafe"
        )

    def test_connect_uses_the_discrete_variables(self, monkeypatch, database_url):
        """A connection opened from DB_* variables reaches the same database."""
        settings = conninfo.conninfo_to_dict(database_url)
        monkeypatch.setenv("DB_HOST", settings.get("host", "localhost"))
        monkeypatch.setenv("DB_PORT", str(settings.get("port", 5432)))
        monkeypatch.setenv("DB_NAME", settings["dbname"])
        if settings.get("user"):
            monkeypatch.setenv("DB_USER", settings["user"])
        if settings.get("password"):
            monkeypatch.setenv("DB_PASSWORD", settings["password"])

        connection = db.connect()
        try:
            assert isinstance(connection, psycopg.Connection)
            assert connection.execute("SELECT 1").fetchone()[0] == 1
        finally:
            connection.close()

    def test_no_credentials_are_hard_coded_in_src(self):
        """The only connection default is a local, password-free URL."""
        assert "@" not in db.DEFAULT_DATABASE_URL
        assert "password" not in db.DEFAULT_DATABASE_URL.lower()


class TestSchemaIsAnAdminTask:
    """The application role never needs DDL at runtime."""

    def test_table_exists_detects_the_table(self, conn):
        assert load_data.table_exists(conn) is True

    def test_table_exists_detects_a_missing_table(self, conn):
        with conn.cursor() as cur:
            cur.execute("DROP TABLE applicants")
        conn.commit()

        assert load_data.table_exists(conn) is False

    def test_ensure_schema_only_issues_ddl_when_needed(self, conn):
        """The second call is a no-op, so no CREATE is sent to the server."""
        with conn.cursor() as cur:
            cur.execute("DROP TABLE applicants")
        conn.commit()

        assert load_data.ensure_schema(conn) is True
        assert load_data.ensure_schema(conn) is False
