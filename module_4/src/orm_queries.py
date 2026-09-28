"""The Module-3 SQLAlchemy ORM report.

Answers a subset of the analysis questions through the ORM instead of raw SQL,
demonstrating that both access paths agree.  Run it with
``python -m src.orm_queries``.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from .models import Applicant, get_db_session
from .query_data import format_count, format_float, format_percent

_ACCEPTED = or_(
    Applicant.status.ilike("%accepted%"),
    Applicant.status.ilike("%acceptance%"),
)


def _percent(part: int, whole: int) -> float:
    """Return ``part / whole`` as a percentage, guarding against division by zero."""
    return (part * 100.0 / whole) if whole else 0.0


def run_orm_queries(
    session: Optional[Session] = None,
    database_url: Optional[str] = None,
    verbose: bool = True,
) -> Dict[str, Any]:
    """Run the ORM report and return its answers.

    :param session: an existing ORM session to reuse; one is opened and closed
        for you when omitted.
    :param database_url: connection-string override used to open a session.
    :param verbose: print the formatted answers to stdout.
    :returns: dict of raw (unformatted) answers.
    """
    if session is None:
        owned = get_db_session(database_url)
        try:
            return run_orm_queries(session=owned, verbose=verbose)
        finally:
            owned.close()

    fall_2026 = session.execute(
        select(func.count(Applicant.p_id)).where(Applicant.term.ilike("%Fall 2026%"))
    ).scalar_one()

    avg_gpa_american_fall_2026 = session.execute(
        select(func.avg(Applicant.gpa)).where(
            and_(
                Applicant.term.ilike("%Fall 2026%"),
                Applicant.us_or_international.ilike("american"),
                Applicant.gpa.is_not(None),
            )
        )
    ).scalar()

    fall_2025_total = session.execute(
        select(func.count(Applicant.p_id)).where(Applicant.term.ilike("%Fall 2025%"))
    ).scalar_one()
    fall_2025_accepted = session.execute(
        select(func.count(Applicant.p_id)).where(
            and_(Applicant.term.ilike("%Fall 2025%"), _ACCEPTED)
        )
    ).scalar_one()

    phd_cs_acceptances = session.execute(
        select(func.count(Applicant.p_id)).where(
            and_(
                Applicant.term.ilike("%2026%"),
                _ACCEPTED,
                Applicant.degree.ilike("%phd%"),
                Applicant.program.ilike("%Computer Science%"),
            )
        )
    ).scalar_one()

    llm_phd_cs_acceptances = session.execute(
        select(func.count(Applicant.p_id)).where(
            and_(
                Applicant.term.ilike("%2026%"),
                _ACCEPTED,
                Applicant.degree.ilike("%phd%"),
                Applicant.llm_generated_program.ilike("%Computer Science%"),
            )
        )
    ).scalar_one()

    high_gpa_total = session.execute(
        select(func.count(Applicant.p_id)).where(Applicant.gpa >= 3.8)
    ).scalar_one()
    high_gpa_accepted = session.execute(
        select(func.count(Applicant.p_id)).where(and_(Applicant.gpa >= 3.8, _ACCEPTED))
    ).scalar_one()

    results: Dict[str, Any] = {
        "fall_2026_count": fall_2026,
        "avg_gpa_american_fall_2026": avg_gpa_american_fall_2026,
        "fall_2025_acceptance_percent": _percent(fall_2025_accepted, fall_2025_total),
        "fall_2026_phd_cs_acceptances": phd_cs_acceptances,
        "llm_fall_2026_phd_cs_acceptances": llm_phd_cs_acceptances,
        "acceptance_percent_high_gpa": _percent(high_gpa_accepted, high_gpa_total),
    }

    if verbose:
        print(f"ORM Fall 2026 applicant count: {format_count(results['fall_2026_count'])}")
        print(
            "ORM average GPA, American Fall 2026: "
            f"{format_float(results['avg_gpa_american_fall_2026'])}"
        )
        print(
            "ORM Fall 2025 acceptance percentage: "
            f"{format_percent(results['fall_2025_acceptance_percent'])}"
        )
        print(
            "ORM Fall 2026 PhD CS acceptances (original fields): "
            f"{format_count(results['fall_2026_phd_cs_acceptances'])}"
        )
        print(
            "ORM Fall 2026 PhD CS acceptances (LLM fields): "
            f"{format_count(results['llm_fall_2026_phd_cs_acceptances'])}"
        )
        print(
            "ORM acceptance percentage, GPA >= 3.80: "
            f"{format_percent(results['acceptance_percent_high_gpa'])}"
        )

    return results


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    run_orm_queries()
