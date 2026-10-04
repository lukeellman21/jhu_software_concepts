"""Reporting layer: the SQL behind the analysis page.

Security model
--------------
Every statement in this module is built with :mod:`psycopg.sql` composition and
is executed separately from its values:

* identifiers (table and column names) go through :class:`psycopg.sql.Identifier`,
  which quotes them safely, and are additionally restricted to the allow-lists
  :data:`ROW_KEYS` and :data:`SEARCHABLE_COLUMNS`;
* every user-supplied value is bound with :class:`psycopg.sql.Placeholder` and
  passed to ``cursor.execute`` as a parameter, so it can never be parsed as SQL;
* no statement is built with an f-string, ``+`` concatenation or ``.format()``
  on raw SQL text;
* every statement carries a ``LIMIT``, and the limit itself is clamped to
  :data:`MIN_LIMIT`..:data:`MAX_LIMIT` by :func:`clamp_limit`.

Each question rendered on ``/analysis`` is declared once as an
:class:`AnalysisSpec`, which drives the raw values (:func:`get_analysis`), the
formatted answers (:func:`get_analysis_items`) and the command-line report
(:func:`run_queries`).
"""
from __future__ import annotations

from typing import Any, Dict, List, NamedTuple, Optional, Sequence, Tuple

import psycopg
from psycopg import sql

from . import db, load_data

#: Table every statement in this module reads from.
TABLE_NAME = "applicants"

#: Smallest row limit a caller may ask for.
MIN_LIMIT = 1

#: Largest row limit a caller may ask for, however large the request.
MAX_LIMIT = 100

#: Limit used when the caller supplies nothing usable.
DEFAULT_LIMIT = 10

#: Aggregate queries return a single row; they are still capped explicitly.
AGGREGATE_LIMIT = 1


class AnalysisSpec(NamedTuple):
    """One question on the analysis page.

    :param key: key used in the analysis dictionary and the template.
    :param question: question text rendered next to the ``Answer:`` label.
    :param kind: ``"count"``, ``"percent"`` or ``"float"``; selects the
        formatter used by :func:`format_answer`.
    :param statement: composed, parameterised SQL returning one scalar value.
    :param params: values bound to ``statement`` at execution time.
    """

    key: str
    question: str
    kind: str
    statement: sql.Composable
    params: Tuple[Any, ...]


#: Columns of ``applicants`` that :func:`get_recent_rows` returns, and the only
#: identifiers accepted for sorting.  Derived from the table definition so the
#: two can never drift apart.
ROW_KEYS: Sequence[str] = load_data.COLUMNS

#: The only columns a free-text search is allowed to match against.
SEARCHABLE_COLUMNS: Sequence[str] = ("program", "status", "term", "degree")

#: Status values that count as an acceptance, bound as parameters.
_ACCEPTED_PATTERNS = ("%accepted%", "%acceptance%")

#: Universities Module 3's questions 8 and 9 ask about.  The abbreviations use
#: the PostgreSQL word-boundary operator so ``MIT`` does not match "Smith".
_TARGET_UNIVERSITY_LIKE = (
    "%Georgetown%",
    "%Massachusetts Institute of Technology%",
    "%Stanford%",
    "%Carnegie Mellon%",
)
_TARGET_UNIVERSITY_REGEX = (r"\yMIT\y", r"\yCMU\y")


def clamp_limit(value: Any, default: int = DEFAULT_LIMIT) -> int:
    """Clamp a requested row limit into :data:`MIN_LIMIT`..:data:`MAX_LIMIT`.

    Anything that is not a whole number (``None``, ``"abc"``, ``"10; DROP
    TABLE"``, ``3.5``) falls back to ``default``, so an oversized or malformed
    request can never widen a query.

    :param value: the requested limit, typically straight from a query string.
    :param default: limit used when ``value`` is unusable.
    :returns: an int in ``[MIN_LIMIT, MAX_LIMIT]``.
    """
    try:
        limit = int(str(value).strip())
    except (TypeError, ValueError):
        limit = default
    return max(MIN_LIMIT, min(MAX_LIMIT, limit))


#: A predicate paired with the parameters it binds, in binding order.
Clause = Tuple[sql.Composable, Tuple[Any, ...]]


def _accepted_clause() -> Clause:
    """Return the "is an acceptance" predicate and its bound patterns."""
    clause = sql.SQL("({col} ILIKE {a} OR {col} ILIKE {b})").format(
        col=sql.Identifier("status"),
        a=sql.Placeholder(),
        b=sql.Placeholder(),
    )
    return clause, _ACCEPTED_PATTERNS


def _university_clause(column: str) -> Clause:
    """Return the target-university predicate for ``column`` and its parameters.

    :param column: column to match against; quoted with
        :class:`psycopg.sql.Identifier`.
    """
    identifier = sql.Identifier(column)
    parts = [
        sql.SQL("{col} ILIKE {val}").format(col=identifier, val=sql.Placeholder())
        for _ in _TARGET_UNIVERSITY_LIKE
    ]
    parts += [
        sql.SQL("{col} ~* {val}").format(col=identifier, val=sql.Placeholder())
        for _ in _TARGET_UNIVERSITY_REGEX
    ]
    clause = sql.SQL("({})").format(sql.SQL(" OR ").join(parts))
    return clause, _TARGET_UNIVERSITY_LIKE + _TARGET_UNIVERSITY_REGEX


def _scalar(expression: sql.Composable, where: Optional[sql.Composable] = None) -> sql.Composable:
    """Compose ``SELECT <expression> FROM applicants [WHERE ...] LIMIT %s``.

    :param expression: the aggregate expression to select.
    :param where: optional predicate.
    :returns: a composed statement whose final placeholder is the row limit.
    """
    statement = sql.SQL("SELECT {expr} FROM {table}").format(
        expr=expression, table=sql.Identifier(TABLE_NAME)
    )
    if where is not None:
        statement = sql.SQL(" ").join([statement, sql.SQL("WHERE {}").format(where)])
    return sql.SQL(" ").join([statement, sql.SQL("LIMIT {}").format(sql.Placeholder())])


def _count_where(where: Optional[Clause] = None) -> Clause:
    """Compose a ``COUNT(*)`` over an optional predicate."""
    where_sql, params = where if where is not None else (None, ())
    return _scalar(sql.SQL("COUNT(*)"), where_sql), params


def _avg_where(column: str, where: Optional[Clause] = None) -> Clause:
    """Compose an ``AVG(column)`` over an optional predicate, ignoring NULLs."""
    where_sql, params = where if where is not None else (None, ())
    not_null = sql.SQL("{} IS NOT NULL").format(sql.Identifier(column))
    predicate = (
        not_null if where_sql is None else sql.SQL(" AND ").join([where_sql, not_null])
    )
    expression = sql.SQL("AVG({})").format(sql.Identifier(column))
    return _scalar(expression, predicate), params


def _percent_where(
    numerator: Clause,
    *,
    denominator: Optional[Clause] = None,
    where: Optional[Clause] = None,
) -> Clause:
    """Compose ``count(numerator) * 100 / nullif(count(denominator), 0)``.

    :param numerator: predicate counted in the numerator, with its parameters.
    :param denominator: optional predicate counted in the denominator; the
        default counts every row.
    :param where: optional predicate restricting the whole query.
    :returns: the composed statement and its parameters, in binding order.
    """
    numerator_sql, numerator_params = numerator
    denominator_sql = (
        sql.SQL("COUNT(*)")
        if denominator is None
        else sql.SQL("COUNT(*) FILTER (WHERE {})").format(denominator[0])
    )
    denominator_params = () if denominator is None else denominator[1]
    where_sql, where_params = where if where is not None else (None, ())

    expression = sql.SQL(
        "COUNT(*) FILTER (WHERE {num}) * 100.0 / NULLIF({den}, 0)"
    ).format(num=numerator_sql, den=denominator_sql)
    return (
        _scalar(expression, where_sql),
        numerator_params + denominator_params + where_params,
    )


def escape_like(term: str) -> str:
    """Escape ``LIKE`` wildcards so a search term is matched literally.

    Without this, a search for ``%`` would match every row.  Parameter binding
    already prevents injection; this prevents a user widening their own query.

    :param term: raw search term.
    :returns: the term with backslash, ``%`` and ``_`` escaped.
    """
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _ilike(column: str, pattern: str) -> Clause:
    """Compose ``column ILIKE %s`` with the pattern bound as a parameter."""
    clause = sql.SQL("{col} ILIKE {val}").format(
        col=sql.Identifier(column), val=sql.Placeholder()
    )
    return clause, (pattern,)


def _and(*clauses: Clause) -> Clause:
    """Join predicates with ``AND``, concatenating their parameters in order."""
    joined = sql.SQL(" AND ").join([clause for clause, _ in clauses])
    params: Tuple[Any, ...] = ()
    for _, clause_params in clauses:
        params += clause_params
    return joined, params


def _predicates() -> Dict[str, Clause]:
    """Build every reusable predicate once, each with its bound parameters."""
    origin = sql.Identifier("us_or_international")
    return {
        "accepted": _accepted_clause(),
        "fall_2026": _ilike("term", "%Fall 2026%"),
        "fall_2025": _ilike("term", "%Fall 2025%"),
        "year_2026": _ilike("term", "%2026%"),
        "phd": _ilike("degree", "%phd%"),
        "masters": _ilike("degree", "%master%"),
        "american": _ilike("us_or_international", "american"),
        "cs_program": _ilike("program", "%Computer Science%"),
        "cs_llm": _ilike("llm_generated_program", "%Computer Science%"),
        "jhu": _ilike("program", "%Johns Hopkins%"),
        "university_program": _university_clause("program"),
        "university_llm": _university_clause("llm_generated_university"),
        "international": _ilike("us_or_international", "international"),
        "origin_known": (
            sql.SQL(
                "{col} IS NOT NULL AND TRIM({col}) <> {empty} AND {col} <> {unknown}"
            ).format(col=origin, empty=sql.Placeholder(), unknown=sql.Placeholder()),
            ("", "Unknown"),
        ),
        "high_gpa": (
            sql.SQL("{col} >= {val}").format(
                col=sql.Identifier("gpa"), val=sql.Placeholder()
            ),
            (3.8,),
        ),
        "low_gpa": (
            sql.SQL("{col} < {val}").format(
                col=sql.Identifier("gpa"), val=sql.Placeholder()
            ),
            (3.8,),
        ),
    }


def _build_specs() -> Tuple[AnalysisSpec, ...]:
    """Compose every analysis statement once, at import time."""
    p = _predicates()

    declarations = (
        ("total_applicants",
         "How many applicant entries are stored in the database?",
         "count", _count_where()),
        ("fall_2026_count",
         "How many entries applied for Fall 2026?",
         "count", _count_where(p["fall_2026"])),
        ("percent_international",
         "What percentage of entries are from international students?",
         "percent",
         _percent_where(p["international"], denominator=p["origin_known"])),
        ("overall_acceptance_percent",
         "What percentage of all entries report an acceptance?",
         "percent", _percent_where(p["accepted"])),
        ("avg_gpa",
         "What is the average GPA across all entries that reported one?",
         "float", _avg_where("gpa")),
        ("avg_gre",
         "What is the average GRE Quantitative score?",
         "float", _avg_where("gre")),
        ("avg_gre_v",
         "What is the average GRE Verbal score?",
         "float", _avg_where("gre_v")),
        ("avg_gre_aw",
         "What is the average GRE Analytical Writing score?",
         "float", _avg_where("gre_aw")),
        ("avg_gpa_american_fall_2026",
         "What is the average GPA of American students applying for Fall 2026?",
         "float", _avg_where("gpa", _and(p["fall_2026"], p["american"]))),
        ("fall_2025_acceptance_percent",
         "What percentage of Fall 2025 entries are acceptances?",
         "percent", _percent_where(p["accepted"], where=p["fall_2025"])),
        ("avg_gpa_accepted_fall_2026",
         "What is the average GPA of Fall 2026 acceptances?",
         "float", _avg_where("gpa", _and(p["fall_2026"], p["accepted"]))),
        ("jhu_masters_cs_count",
         "How many entries are JHU Masters applications in Computer Science?",
         "count", _count_where(_and(p["jhu"], p["cs_program"], p["masters"]))),
        ("fall_2026_phd_cs_acceptances",
         "How many 2026 PhD Computer Science acceptances are there at Georgetown, "
         "MIT, Stanford or Carnegie Mellon (original fields)?",
         "count",
         _count_where(_and(p["year_2026"], p["accepted"], p["phd"],
                           p["cs_program"], p["university_program"]))),
        ("llm_fall_2026_phd_cs_acceptances",
         "How many 2026 PhD Computer Science acceptances are there at Georgetown, "
         "MIT, Stanford or Carnegie Mellon (LLM-standardised fields)?",
         "count",
         _count_where(_and(p["year_2026"], p["accepted"], p["phd"],
                           p["cs_llm"], p["university_llm"]))),
        ("avg_gpa_phd",
         "What is the average GPA of PhD applicants?",
         "float", _avg_where("gpa", p["phd"])),
        ("avg_gpa_masters",
         "What is the average GPA of Masters applicants?",
         "float", _avg_where("gpa", p["masters"])),
        ("acceptance_percent_high_gpa",
         "What percentage of applicants with a GPA of 3.80 or higher were accepted?",
         "percent", _percent_where(p["accepted"], where=p["high_gpa"])),
        ("acceptance_percent_low_gpa",
         "What percentage of applicants with a GPA below 3.80 were accepted?",
         "percent", _percent_where(p["accepted"], where=p["low_gpa"])),
    )

    return tuple(
        AnalysisSpec(key, question, kind, statement, params)
        for key, question, kind, (statement, params) in declarations
    )


#: Every question on the analysis page, in render order.
ANALYSIS_SPECS: Sequence[AnalysisSpec] = _build_specs()

#: Keys the analysis template expects :func:`get_analysis` to provide.
EXPECTED_KEYS: Sequence[str] = tuple(spec.key for spec in ANALYSIS_SPECS)


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
    """Run every :data:`ANALYSIS_SPECS` statement and return the raw values.

    :param conn: connection to reuse; when ``None`` one is opened from the
        environment and closed before returning.
    :param database_url: connection-string override.
    :returns: dict keyed by :data:`EXPECTED_KEYS`.
    """
    if conn is None:
        with db.connect(database_url) as owned:
            return get_analysis(conn=owned)

    analysis: Dict[str, Any] = {}
    with conn.cursor() as cur:
        for spec in ANALYSIS_SPECS:
            cur.execute(spec.statement, spec.params + (AGGREGATE_LIMIT,))
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


def build_rows_statement(
    sort_by: str = "p_id",
    descending: bool = True,
    search: Optional[str] = None,
) -> Tuple[sql.Composable, Tuple[Any, ...]]:
    """Compose the recent-rows query, separately from executing it.

    The sort column is validated against :data:`ROW_KEYS` and then quoted with
    :class:`psycopg.sql.Identifier`; an unknown column silently falls back to
    ``p_id`` rather than reaching the database.  The search term is never put
    into SQL text: it is bound once per :data:`SEARCHABLE_COLUMNS` column as a
    parameter.

    :param sort_by: column to order by; must be one of :data:`ROW_KEYS`.
    :param descending: sort direction.
    :param search: optional free-text term.
    :returns: ``(statement, params)``; the final placeholder is the row limit.
    """
    column = sort_by if sort_by in ROW_KEYS else "p_id"
    statement = sql.SQL("SELECT {cols} FROM {table}").format(
        cols=sql.SQL(", ").join(sql.Identifier(key) for key in ROW_KEYS),
        table=sql.Identifier(TABLE_NAME),
    )

    params: Tuple[Any, ...] = ()
    term = (search or "").strip()
    if term:
        pattern = f"%{escape_like(term)}%"
        matches = sql.SQL(" OR ").join(
            sql.SQL("{col} ILIKE {val}").format(
                col=sql.Identifier(name), val=sql.Placeholder()
            )
            for name in SEARCHABLE_COLUMNS
        )
        statement = sql.SQL(" ").join(
            [statement, sql.SQL("WHERE ({})").format(matches)]
        )
        params = (pattern,) * len(SEARCHABLE_COLUMNS)

    direction = sql.SQL("DESC") if descending else sql.SQL("ASC")
    statement = sql.SQL(" ").join(
        [
            statement,
            sql.SQL("ORDER BY {col} {dir}").format(
                col=sql.Identifier(column), dir=direction
            ),
            sql.SQL("LIMIT {}").format(sql.Placeholder()),
        ]
    )
    return statement, params


def get_recent_rows(
    limit: Any = DEFAULT_LIMIT,
    *,
    sort_by: str = "p_id",
    descending: bool = True,
    search: Optional[str] = None,
    conn: Optional[psycopg.Connection] = None,
    database_url: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return recent rows as dicts keyed by :data:`ROW_KEYS`.

    :param limit: requested row count; clamped by :func:`clamp_limit`.
    :param sort_by: column to order by, validated against :data:`ROW_KEYS`.
    :param descending: sort direction.
    :param search: optional free-text term, matched as a bound parameter.
    :param conn: connection to reuse; opened from the environment when ``None``.
    :param database_url: connection-string override.
    :returns: at most :data:`MAX_LIMIT` rows.
    """
    if conn is None:
        with db.connect(database_url) as owned:
            return get_recent_rows(
                limit=limit, sort_by=sort_by, descending=descending,
                search=search, conn=owned,
            )

    statement, params = build_rows_statement(sort_by, descending, search)
    with conn.cursor() as cur:
        cur.execute(statement, params + (clamp_limit(limit),))
        return [dict(zip(ROW_KEYS, row)) for row in cur.fetchall()]


def count_rows(
    conn: Optional[psycopg.Connection] = None,
    database_url: Optional[str] = None,
) -> int:
    """Return the number of rows in ``applicants``."""
    if conn is None:
        with db.connect(database_url) as owned:
            return count_rows(conn=owned)
    statement = _scalar(sql.SQL("COUNT(*)"))
    with conn.cursor() as cur:
        cur.execute(statement, (AGGREGATE_LIMIT,))
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
