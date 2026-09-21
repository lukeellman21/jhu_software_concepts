from sqlalchemy import select, func, and_, or_
from models import get_db_session, Applicant

def run_orm_queries():
    session = get_db_session()
    try:
        # Question 1: Fall 2026 Applicants Count
        stmt_q1 = select(func.count(Applicant.p_id)).where(Applicant.term.ilike('%Fall 2026%'))
        q1 = session.execute(stmt_q1).scalar()
        print(f"ORM Fall 2026 applicant count: {q1:,}")

        # Question 4: Average GPA of Fall 2026 American Applicants
        stmt_q4 = select(func.avg(Applicant.gpa)).where(
            and_(
                Applicant.term.ilike('%Fall 2026%'),
                Applicant.us_or_international.ilike('american'),
                Applicant.gpa.is_not(None)
            )
        )
        q4 = session.execute(stmt_q4).scalar()
        print(f"ORM Average GPA American Fall 2026: {q4:.2f}" if q4 else "ORM Average GPA American Fall 2026: N/A")

        # Question 5: Fall 2025 Acceptance Percentage
        stmt_q5_accepted = select(func.count(Applicant.p_id)).where(
            and_(
                Applicant.term.ilike('%Fall 2025%'),
                or_(Applicant.status.ilike('%accepted%'), Applicant.status.ilike('%acceptance%'))
            )
        )
        stmt_q5_total = select(func.count(Applicant.p_id)).where(Applicant.term.ilike('%Fall 2025%'))
        accepted_cnt = session.execute(stmt_q5_accepted).scalar() or 0
        total_cnt = session.execute(stmt_q5_total).scalar() or 0
        q5 = (accepted_cnt * 100.0 / total_cnt) if total_cnt > 0 else 0.0
        print(f"ORM Fall 2025 acceptance percentage: {q5:.2f}%")

        # Question 8: Fall 2026 PhD CS Acceptances (Original Fields)
        stmt_q8 = select(func.count(Applicant.p_id)).where(
            and_(
                Applicant.term.ilike('%Fall 2026%'),
                or_(Applicant.status.ilike('%accepted%'), Applicant.status.ilike('%acceptance%')),
                or_(Applicant.degree.ilike('%phd%'), Applicant.degree.ilike('%ph.d%')),
                Applicant.program.ilike('%Computer Science%'),
                or_(
                    Applicant.program.ilike('%Georgetown%'),
                    Applicant.program.ilike('%Massachusetts Institute of Technology%'),
                    Applicant.program.ilike('%MIT%'),
                    Applicant.program.ilike('%Stanford%'),
                    Applicant.program.ilike('%Carnegie Mellon%'),
                    Applicant.program.ilike('%CMU%')
                )
            )
        )
        q8 = session.execute(stmt_q8).scalar()
        print(f"ORM Original-field count: {q8:,}")

        # Question 9: Fall 2026 PhD CS Acceptances (LLM Fields)
        stmt_q9 = select(func.count(Applicant.p_id)).where(
            and_(
                Applicant.term.ilike('%Fall 2026%'),
                or_(Applicant.status.ilike('%accepted%'), Applicant.status.ilike('%acceptance%')),
                or_(Applicant.degree.ilike('%phd%'), Applicant.degree.ilike('%ph.d%')),
                Applicant.llm_generated_program.ilike('%Computer Science%'),
                or_(
                    Applicant.llm_generated_university.ilike('%Georgetown%'),
                    Applicant.llm_generated_university.ilike('%Massachusetts Institute of Technology%'),
                    Applicant.llm_generated_university.ilike('%MIT%'),
                    Applicant.llm_generated_university.ilike('%Stanford%'),
                    Applicant.llm_generated_university.ilike('%Carnegie Mellon%'),
                    Applicant.llm_generated_university.ilike('%CMU%')
                )
            )
        )
        q9 = session.execute(stmt_q9).scalar()
        diff = q9 - q8
        print(f"ORM LLM-field count: {q9:,}")
        print(f"ORM Difference: {diff:+d}")

        # Custom Question: Acceptance Rate for GPA >= 3.8
        stmt_high_acc = select(func.count(Applicant.p_id)).where(
            and_(Applicant.gpa >= 3.8, or_(Applicant.status.ilike('%accepted%'), Applicant.status.ilike('%acceptance%')))
        )
        stmt_high_tot = select(func.count(Applicant.p_id)).where(Applicant.gpa >= 3.8)
        h_acc = session.execute(stmt_high_acc).scalar() or 0
        h_tot = session.execute(stmt_high_tot).scalar() or 0
        pct = (h_acc * 100.0 / h_tot) if h_tot > 0 else 0.0
        print(f"ORM Custom Q2 - Acceptance (GPA >= 3.8): {pct:.2f}%")

    finally:
        session.close()

if __name__ == "__main__":
    run_orm_queries()