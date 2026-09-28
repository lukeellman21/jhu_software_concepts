"""Reporting layer: the SQL behind the analysis page.

Each question rendered on ``/analysis`` is declared once as an
:class:`AnalysisSpec` -- key, human question, formatting kind and SQL.  That
single declaration drives the raw values (:func:`get_analysis`), the formatted
answers (:func:`get_analysis_items`) and the command-line report
(:func:`run_queries`), so the page and the CLI can never drift apart.
"""
from __future__ import annotations

from typing import Any, Dict, List, NamedTuple, Optional, Sequence

import psycopg

from . import db


class AnalysisSpec(NamedTuple):
    """One question on the analysis page.

    :param key: key used in the analysis dictionary and the template.
    :param question: question text rendered next to the ``Answer:`` label.
    :param kind: ``"count"``, ``"percent"`` or ``"float"``; selects the
        formatter used by :func:`format_answer`.
    :param sql: SQL returning exactly one scalar value.
    """

    key: str
    question: str
    kind: str
    sql: str


_ACCEPTED = "(status ILIKE '%accepted%' OR status ILIKE '%acceptance%')"

#: The universities Module 3's questions 8 and 9 ask about.
#:
#: Full names are matched with ``ILIKE``; the abbreviations use the PostgreSQL
#: word-boundary operator ``~*`` with ``\y`` so that ``MIT`` matches "MIT" but
#: not the "mit" inside "Smith College", which is what made the Module-3
#: counts too high.
_TARGET_UNIVERSITIES = (
    "{column} ILIKE '%Georgetown%'",
    "{column} ILIKE '%Massachusetts Institute of Technology%'",
    r"{column} ~* '\yMIT\y'",
    "{column} ILIKE '%Stanford%'",
    "{column} ILIKE '%Carnegie Mellon%'",
    r"{column} ~* '\yCMU\y'",
)


def _university_filter(column: str) -> str:
    """Return the SQL that restricts ``column`` to :data:`_TARGET_UNIVERSITIES`."""
    return "(" + " OR ".join(clause.format(column=column) for clause in _TARGET_UNIVERSITIES) + ")"

ANALYSIS_SPECS: Sequence[AnalysisSpec] = (
    AnalysisSpec(
        "total_applicants",
        "How many applicant entries are stored in the database?",
        "count",
        "SELECT COUNT(*) FROM applicants;",
    ),
    AnalysisSpec(
        "fall_2026_count",
        "How many entries applied for Fall 2026?",
        "count",
        "SELECT COUNT(*) FROM applicants WHERE term ILIKE '%Fall 2026%';",
    ),
    AnalysisSpec(
        "percent_international",
        "What percentage of entries are from international students?",
        "percent",
        """
        SELECT COUNT(*) FILTER (WHERE us_or_international ILIKE 'international') * 100.0
               / NULLIF(COUNT(*) FILTER (
                     WHERE us_or_international IS NOT NULL
                       AND TRIM(us_or_international) <> ''
                       AND us_or_international <> 'Unknown'), 0)
        FROM applicants;
        """,
    ),
    AnalysisSpec(
        "overall_acceptance_percent",
        "What percentage of all entries report an acceptance?",
        "percent",
        f"SELECT COUNT(*) FILTER (WHERE {_ACCEPTED}) * 100.0 / NULLIF(COUNT(*), 0) FROM applicants;",
    ),
    AnalysisSpec(
        "avg_gpa",
        "What is the average GPA across all entries that reported one?",
        "float",
        "SELECT AVG(gpa) FROM applicants WHERE gpa IS NOT NULL;",
    ),
    AnalysisSpec(
        "avg_gre",
        "What is the average GRE Quantitative score?",
        "float",
        "SELECT AVG(gre) FROM applicants WHERE gre IS NOT NULL;",
    ),
    AnalysisSpec(
        "avg_gre_v",
        "What is the average GRE Verbal score?",
        "float",
        "SELECT AVG(gre_v) FROM applicants WHERE gre_v IS NOT NULL;",
    ),
    AnalysisSpec(
        "avg_gre_aw",
        "What is the average GRE Analytical Writing score?",
        "float",
        "SELECT AVG(gre_aw) FROM applicants WHERE gre_aw IS NOT NULL;",
    ),
    AnalysisSpec(
        "avg_gpa_american_fall_2026",
        "What is the average GPA of American students applying for Fall 2026?",
        "float",
        """
        SELECT AVG(gpa) FROM applicants
        WHERE term ILIKE '%Fall 2026%'
          AND us_or_international ILIKE 'american'
          AND gpa IS NOT NULL;
        """,
    ),
    AnalysisSpec(
        "fall_2025_acceptance_percent",
        "What percentage of Fall 2025 entries are acceptances?",
        "percent",
        f"""
        SELECT COUNT(*) FILTER (WHERE {_ACCEPTED}) * 100.0 / NULLIF(COUNT(*), 0)
        FROM applicants WHERE term ILIKE '%Fall 2025%';
        """,
    ),
    AnalysisSpec(
        "avg_gpa_accepted_fall_2026",
        "What is the average GPA of Fall 2026 acceptances?",
        "float",
        f"""
        SELECT AVG(gpa) FROM applicants
        WHERE term ILIKE '%Fall 2026%' AND {_ACCEPTED} AND gpa IS NOT NULL;
        """,
    ),
    AnalysisSpec(
        "jhu_masters_cs_count",
        "How many entries are JHU Masters applications in Computer Science?",
        "count",
        """
        SELECT COUNT(*) FROM applicants
        WHERE (program ILIKE '%Johns Hopkins%' OR program ILIKE '%JHU%')
          AND program ILIKE '%Computer Science%'
          AND (degree ILIKE '%master%' OR degree ILIKE '%MS%' OR degree ILIKE '%M.S.%');
        """,
    ),
    AnalysisSpec(
        "fall_2026_phd_cs_acceptances",
        "How many 2026 PhD Computer Science acceptances are there at Georgetown, "
        "MIT, Stanford or Carnegie Mellon (original fields)?",
        "count",
        f"""
        SELECT COUNT(*) FROM applicants
        WHERE term ILIKE '%2026%' AND {_ACCEPTED}
          AND (degree ILIKE '%phd%' OR degree ILIKE '%ph.d%')
          AND program ILIKE '%Computer Science%'
          AND {_university_filter('program')};
        """,
    ),
    AnalysisSpec(
        "llm_fall_2026_phd_cs_acceptances",
        "How many 2026 PhD Computer Science acceptances are there at Georgetown, "
        "MIT, Stanford or Carnegie Mellon (LLM-standardised fields)?",
        "count",
        f"""
        SELECT COUNT(*) FROM applicants
        WHERE term ILIKE '%2026%' AND {_ACCEPTED}
          AND (degree ILIKE '%phd%' OR degree ILIKE '%ph.d%')
          AND llm_generated_program ILIKE '%Computer Science%'
          AND {_university_filter('llm_generated_university')};
        """,
    ),
    AnalysisSpec(
        "avg_gpa_phd",
        "What is the average GPA of PhD applicants?",
        "float",
        "SELECT AVG(gpa) FROM applicants WHERE degree ILIKE '%phd%' AND gpa IS NOT NULL;",
    ),
    AnalysisSpec(
        "avg_gpa_masters",
        "What is the average GPA of Masters applicants?",
        "float",
        "SELECT AVG(gpa) FROM applicants WHERE degree ILIKE '%master%' AND gpa IS NOT NULL;",
    ),
    AnalysisSpec(
        "acceptance_percent_high_gpa",
        "What percentage of applicants with a GPA of 3.80 or higher were accepted?",
        "percent",
        f"""
        SELECT COUNT(*) FILTER (WHERE {_ACCEPTED}) * 100.0 / NULLIF(COUNT(*), 0)
        FROM applicants WHERE gpa >= 3.8;
        """,
    ),
    AnalysisSpec(
        "acceptance_percent_low_gpa",
        "What percentage of applicants with a GPA below 3.80 were accepted?",
        "percent",
        f"""
        SELECT COUNT(*) FILTER (WHERE {_ACCEPTED}) * 100.0 / NULLIF(COUNT(*), 0)
        FROM applicants WHERE gpa < 3.8;
        """,
    ),
)

#: Keys the analysis template expects :func:`get_analysis` to provide.
EXPECTED_KEYS: Sequence[str] = tuple(spec.key for spec in ANALYSIS_SPECS)

#: Columns of ``applicants`` that :func:`get_recent_rows` returns.
ROW_KEYS: Sequence[str] = (
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


def format_percent(value: Optional[float]) -> str:
    """Format a percentage with exactly two decimal places, e.g. ``"39.28%"``."""
    return f"{float(value or 0.0):.2f}%"


def format_float(value: Optional[float]) -> str:
    """Format an average with two decimals, or ``"N/A"`` when there is no data."""
    if value is None:
        return "N/A"
    return f"{float(value):.2f}"


def format_count(value: Optional[int]) -> str:
    """Format a row count with thousands separators."""
    return f"{int(value or 0):,}"


def format_answer(kind: str, value: Any) -> str:
    """Format ``value`` according to an :class:`AnalysisSpec` ``kind``."""
    if kind == "percent":
        return format_percent(value)
    if kind == "count":
        return format_count(value)
    return format_float(value)


def get_analysis(
    conn: Optional[psycopg.Connection] = None,
    database_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Run every :data:`ANALYSIS_SPECS` query and return the raw values.

    :param conn: connection to reuse; when ``None`` one is opened from
        ``DATABASE_URL`` and closed before returning.
    :param database_url: connection-string override.
    :returns: dict keyed by :data:`EXPECTED_KEYS`; counts are ints, averages and
        percentages are floats or ``None`` when the query matched no rows.
    """
    if conn is None:
        with db.connect(database_url) as owned:
            return get_analysis(conn=owned)

    analysis: Dict[str, Any] = {}
    with conn.cursor() as cur:
        for spec in ANALYSIS_SPECS:
            cur.execute(spec.sql)
            row = cur.fetchone()
            value = row[0] if row else None
            analysis[spec.key] = int(value or 0) if spec.kind == "count" else value
    return analysis


def get_analysis_items(analysis: Dict[str, Any]) -> List[Dict[str, str]]:
    """Pair each question with its formatted answer, ready for the template.

    :param analysis: output of :func:`get_analysis`.
    :returns: list of ``{"key", "question", "answer"}`` dicts in page order.
    """
    return [
        {
            "key": spec.key,
            "question": spec.question,
            "answer": format_answer(spec.kind, analysis.get(spec.key)),
        }
        for spec in ANALYSIS_SPECS
    ]


def get_recent_rows(
    limit: int = 10,
    conn: Optional[psycopg.Connection] = None,
    database_url: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return the most recently loaded rows as dicts keyed by :data:`ROW_KEYS`.

    :param limit: maximum number of rows to return.
    :param conn: connection to reuse; opened from ``DATABASE_URL`` when ``None``.
    :param database_url: connection-string override.
    """
    if conn is None:
        with db.connect(database_url) as owned:
            return get_recent_rows(limit=limit, conn=owned)

    columns = ", ".join(ROW_KEYS)
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT {columns} FROM applicants ORDER BY p_id DESC LIMIT %s;",
            (limit,),
        )
        return [dict(zip(ROW_KEYS, row)) for row in cur.fetchall()]


def count_rows(
    conn: Optional[psycopg.Connection] = None,
    database_url: Optional[str] = None,
) -> int:
    """Return the number of rows in ``applicants``."""
    if conn is None:
        with db.connect(database_url) as owned:
            return count_rows(conn=owned)
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM applicants;")
        return int(cur.fetchone()[0])


def run_queries(database_url: Optional[str] = None) -> Dict[str, Any]:
    """Print every question and answer to stdout and return the raw analysis.

    This is the command-line equivalent of the ``/analysis`` page:
    ``python -m src.query_data``.
    """
    analysis = get_analysis(database_url=database_url)
    for item in get_analysis_items(analysis):
        print(f"{item['question']}\nAnswer: {item['answer']}\n")
    return analysis


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    run_queries()
