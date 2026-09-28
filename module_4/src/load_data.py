"""ETL load layer: normalise Grad Café records and write them to PostgreSQL.

The module owns three responsibilities:

1. the ``applicants`` table definition (:data:`CREATE_TABLE_SQL`),
2. turning a raw scraped/cleaned record into a database row
   (:func:`normalize_record`),
3. an idempotent bulk insert (:func:`insert_rows`).

Uniqueness policy
-----------------
``p_id`` is the primary key and is *derived* from the record rather than
assigned by the database: the numeric id inside the Grad Café result URL when
one is present, otherwise a deterministic hash of the record's identifying
fields (see :func:`derive_p_id`).  Inserts use ``ON CONFLICT (p_id) DO
NOTHING``, so re-pulling data that is already stored is a no-op.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence

import psycopg

from . import db

TABLE_NAME = "applicants"

#: Columns that may never be ``NULL``; :func:`normalize_record` always fills them.
REQUIRED_FIELDS: Sequence[str] = (
    "p_id",
    "program",
    "comments",
    "url",
    "status",
    "term",
    "us_or_international",
    "degree",
)

#: Every column of the ``applicants`` table, in insert order.
COLUMNS: Sequence[str] = (
    "p_id",
    "program",
    "comments",
    "date_added",
    "url",
    "status",
    "term",
    "us_or_international",
    "gpa",
    "gre",
    "gre_v",
    "gre_aw",
    "degree",
    "llm_generated_program",
    "llm_generated_university",
)

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS applicants (
    p_id INTEGER PRIMARY KEY,
    program TEXT NOT NULL,
    comments TEXT NOT NULL,
    date_added DATE,
    url TEXT NOT NULL,
    status TEXT NOT NULL,
    term TEXT NOT NULL,
    us_or_international TEXT NOT NULL,
    gpa FLOAT,
    gre FLOAT,
    gre_v FLOAT,
    gre_aw FLOAT,
    degree TEXT NOT NULL,
    llm_generated_program TEXT,
    llm_generated_university TEXT
);
"""

DROP_TABLE_SQL = "DROP TABLE IF EXISTS applicants;"

INSERT_ROW_SQL = """
INSERT INTO applicants (
    p_id, program, comments, date_added, url, status, term,
    us_or_international, gpa, gre, gre_v, gre_aw, degree,
    llm_generated_program, llm_generated_university
) VALUES (
    %(p_id)s, %(program)s, %(comments)s, %(date_added)s, %(url)s, %(status)s, %(term)s,
    %(us_or_international)s, %(gpa)s, %(gre)s, %(gre_v)s, %(gre_aw)s, %(degree)s,
    %(llm_generated_program)s, %(llm_generated_university)s
)
ON CONFLICT (p_id) DO NOTHING;
"""

#: Default dataset shipped with the repository so the loader never needs the network.
DEFAULT_DATA_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "sample_applicant_data.json",
)

_DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%d-%b-%Y", "%B %d, %Y", "%b %d, %Y")

#: Printed when the loader cannot reach PostgreSQL, so the operator knows what to fix.
CONNECTION_HELP = (
    "Could not connect to PostgreSQL at {url}.\n"
    "  1. Is the server running?  Check with `pg_isready`.\n"
    "  2. Does the database exist?  Create it with `createdb gradcafe`.\n"
    "  3. Is DATABASE_URL correct?  It is read from the environment.\n"
    "Nothing was loaded; re-run once the server is reachable.\n"
    "Original error: {error}"
)


def extract_degree(text: Optional[str]) -> str:
    """Map a free-text program string onto ``PhD`` / ``Masters`` / ``Other``."""
    if not text:
        return "Other"
    lowered = text.lower()
    if "phd" in lowered or "ph.d" in lowered or "doctorate" in lowered:
        return "PhD"
    if any(token in lowered for token in ("master", "ms", "m.s.", "mfa", "ma", "m.a.")):
        return "Masters"
    return "Other"


def extract_university_and_program(raw: Optional[str]) -> tuple[str, str]:
    """Split ``"University - Program"`` into its two halves."""
    if not raw:
        return "Unknown", "Unknown"
    parts = raw.split(" - ")
    if len(parts) >= 2:
        return parts[0].strip(), " - ".join(parts[1:]).strip()
    return raw.strip(), raw.strip()


def normalize_status(value: Optional[str]) -> str:
    """Collapse the free-text decision column onto a small, queryable vocabulary."""
    if not value:
        return "Applied"
    lowered = str(value).lower()
    if "accept" in lowered:
        return "Accepted"
    if "reject" in lowered or "denied" in lowered:
        return "Rejected"
    if "interview" in lowered:
        return "Interview"
    if "wait" in lowered:
        return "Waitlisted"
    return "Applied"


def parse_float(value: Any) -> Optional[float]:
    """Parse a float out of messy input, returning ``None`` when impossible."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = re.sub(r"[^\d.]", "", str(value))
    try:
        return float(cleaned) if cleaned else None
    except ValueError:
        # e.g. "1.2.3" survives the character filter but is not a float.
        return None


def parse_date(value: Any) -> Optional[date]:
    """Parse the Grad Café ``date_added`` column into a :class:`datetime.date`."""
    if not value:
        return None
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def derive_p_id(record: Dict[str, Any], fallback: int = 0) -> int:
    """Derive the primary key for a record.

    The Grad Café result URL (``.../result/1020482``) carries a stable numeric
    id, which makes re-pulled records collapse onto the same row.  When no URL
    is available a deterministic hash of the identifying fields is used so that
    the same record still maps to the same ``p_id`` on every pull.

    :param record: raw or normalised record.
    :param fallback: value returned when the record carries no identity at all.
    """
    explicit = record.get("p_id") or record.get("id")
    if explicit is not None:
        try:
            return int(explicit)
        except (TypeError, ValueError):
            pass

    url = record.get("url") or ""
    match = re.search(r"(\d{3,})", str(url))
    if match:
        return int(match.group(1))

    fingerprint = "|".join(
        str(record.get(key) or "")
        for key in ("program", "comments", "date_added", "status")
    ).strip("|")
    if not fingerprint:
        return fallback
    digest = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 2_000_000_000


def normalize_record(record: Dict[str, Any], index: int = 1) -> Dict[str, Any]:
    """Turn one raw record into a fully populated ``applicants`` row.

    Accepts both the scraper's raw key names (``"GPA"``, ``"US/International"``,
    ``"llm-generated-program"``) and the database column names, so cleaned data
    and re-read database rows both normalise cleanly.  Every column listed in
    :data:`REQUIRED_FIELDS` is guaranteed to be non-``NULL`` on the way out.

    :param record: the raw record.
    :param index: 1-based position in the batch, used only as a last-resort id.
    :returns: a dict keyed by :data:`COLUMNS`.
    """

    def pick(*keys: str) -> Any:
        for key in keys:
            value = record.get(key)
            if value not in (None, ""):
                return value
        return None

    raw_program = pick("program") or "Unknown Program"
    university, program_name = extract_university_and_program(raw_program)
    degree = pick("degree", "Degree") or extract_degree(raw_program)

    return {
        "p_id": derive_p_id(record, fallback=index),
        "program": str(raw_program),
        "comments": str(pick("comments") or ""),
        "date_added": parse_date(pick("date_added")),
        "url": str(pick("url") or ""),
        "status": normalize_status(pick("status")),
        "term": str(pick("term") or "Unknown"),
        "us_or_international": str(
            pick("us_or_international", "US/International") or "Unknown"
        ),
        "gpa": parse_float(pick("gpa", "GPA")),
        "gre": parse_float(pick("gre", "GRE")),
        "gre_v": parse_float(pick("gre_v", "GRE V")),
        "gre_aw": parse_float(pick("gre_aw", "GRE AW")),
        "degree": str(degree),
        "llm_generated_program": str(
            pick("llm_generated_program", "llm-generated-program") or program_name
        ),
        "llm_generated_university": str(
            pick("llm_generated_university", "llm-generated-university") or university
        ),
    }


def normalize_records(records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normalise a batch of records with :func:`normalize_record`."""
    return [normalize_record(record, index) for index, record in enumerate(records, start=1)]


def ensure_schema(conn: psycopg.Connection) -> None:
    """Create the ``applicants`` table when it does not already exist."""
    with conn.cursor() as cur:
        cur.execute(CREATE_TABLE_SQL)
    conn.commit()


def reset_schema(conn: psycopg.Connection) -> None:
    """Drop and recreate the ``applicants`` table (used by tests and re-seeds)."""
    with conn.cursor() as cur:
        cur.execute(DROP_TABLE_SQL)
        cur.execute(CREATE_TABLE_SQL)
    conn.commit()


def insert_rows(
    records: Iterable[Dict[str, Any]],
    conn: Optional[psycopg.Connection] = None,
    database_url: Optional[str] = None,
    normalize: bool = True,
) -> int:
    """Insert records into ``applicants`` and return how many rows were new.

    The insert is idempotent: rows whose ``p_id`` already exists are skipped by
    ``ON CONFLICT (p_id) DO NOTHING``, so the returned count is the number of
    genuinely new rows rather than the number of records supplied.

    :param records: raw records (``normalize=True``) or ready-made rows.
    :param conn: an existing connection to reuse; when ``None`` a new one is
        opened from ``DATABASE_URL`` and closed again before returning.
    :param database_url: connection-string override used when ``conn is None``.
    :param normalize: run :func:`normalize_record` over each record first.
    :returns: number of rows inserted.
    :raises psycopg.Error: the whole batch is rolled back on any failure.
    """
    rows = normalize_records(records) if normalize else list(records)

    if conn is None:
        with db.connect(database_url) as owned:
            return insert_rows(rows, conn=owned, normalize=False)

    ensure_schema(conn)
    inserted = 0
    try:
        with conn.cursor() as cur:
            for row in rows:
                cur.execute(INSERT_ROW_SQL, row)
                inserted += cur.rowcount
        conn.commit()
    except psycopg.Error:
        conn.rollback()
        raise
    return inserted


def read_records(path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Read a JSON array of records from disk.

    :param path: file to read; defaults to :data:`DEFAULT_DATA_FILE` (or the
        ``GRADCAFE_DATA_FILE`` environment variable when set).
    """
    file_path = path or os.environ.get("GRADCAFE_DATA_FILE") or DEFAULT_DATA_FILE
    with open(file_path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def load_data(
    path: Optional[str] = None,
    database_url: Optional[str] = None,
    reset: bool = False,
) -> int:
    """Load a JSON dataset from disk into PostgreSQL.

    :param path: dataset to read, see :func:`read_records`.
    :param database_url: connection-string override.
    :param reset: drop and recreate the table before loading.
    :returns: number of rows inserted.
    """
    records = read_records(path)
    with db.connect(database_url) as conn:
        if reset:
            reset_schema(conn)
        return insert_rows(records, conn=conn)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Command-line entry point: ``python -m src.load_data --reset``.

    :param argv: argument list; ``None`` reads ``sys.argv``.
    :returns: ``0`` when the load succeeded, ``1`` when the database could not
        be reached.  ``__main__`` passes the value to :class:`SystemExit`, so a
        failed load exits non-zero.
    """
    parser = argparse.ArgumentParser(description="Load Grad Café records into PostgreSQL.")
    parser.add_argument("--file", dest="path", default=None, help="JSON dataset to load")
    parser.add_argument("--reset", action="store_true", help="drop and recreate the table first")
    args = parser.parse_args(argv)

    try:
        inserted = load_data(path=args.path, reset=args.reset)
    except psycopg.OperationalError as exc:
        print(CONNECTION_HELP.format(url=db.get_database_url(), error=exc), file=sys.stderr)
        return 1

    print(f"Inserted {inserted} new row(s) into {TABLE_NAME}.")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
