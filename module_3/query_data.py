import os
import psycopg

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost/gradcafe")

QUERIES = {
    "Q1": {
        "title": "Question 1: Fall 2026 Applicants Count",
        "sql": "SELECT COUNT(*) FROM applicants WHERE term ILIKE '%Fall 2026%';"
    },
    "Q2": {
        "title": "Question 2: Percent International Applicants",
        "sql": """
            SELECT 
                COUNT(*) FILTER (WHERE us_or_international ILIKE 'international') * 100.0 / 
                NULLIF(COUNT(*) FILTER (WHERE us_or_international IS NOT NULL AND TRIM(us_or_international) <> ''), 0)
            FROM applicants;
        """
    },
    "Q3": {
        "title": "Question 3: Average Metrics (GPA, GRE Q, GRE V, GRE AW)",
        "sql": "SELECT AVG(gpa), AVG(gre), AVG(gre_v), AVG(gre_aw) FROM applicants;"
    },
    "Q4": {
        "title": "Question 4: Average GPA of Fall 2026 American Applicants",
        "sql": """
            SELECT AVG(gpa) FROM applicants 
            WHERE term ILIKE '%Fall 2026%' 
              AND us_or_international ILIKE 'american' 
              AND gpa IS NOT NULL;
        """
    },
    "Q5": {
        "title": "Question 5: Fall 2025 Acceptance Percentage",
        "sql": """
            SELECT 
                COUNT(*) FILTER (WHERE status ILIKE '%accepted%' OR status ILIKE '%acceptance%') * 100.0 / 
                NULLIF(COUNT(*), 0)
            FROM applicants 
            WHERE term ILIKE '%Fall 2025%';
        """
    },
    "Q6": {
        "title": "Question 6: Average GPA of Accepted Fall 2026 Applicants",
        "sql": """
            SELECT AVG(gpa) FROM applicants 
            WHERE term ILIKE '%Fall 2026%' 
              AND (status ILIKE '%accepted%' OR status ILIKE '%acceptance%')
              AND gpa IS NOT NULL;
        """
    },
    "Q7": {
        "title": "Question 7: JHU Master's in Computer Science Count (Original Fields)",
        "sql": """
            SELECT COUNT(*) FROM applicants 
            WHERE (program ILIKE '%Johns Hopkins%' OR program ILIKE '%JHU%')
              AND program ILIKE '%Computer Science%'
              AND (degree ILIKE '%master%' OR degree ILIKE '%MS%' OR degree ILIKE '%M.S.%');
        """
    },
    "Q8": {
        "title": "Question 8: Fall 2026 PhD CS Acceptances (Original Fields)",
        "sql": """
            SELECT COUNT(*) FROM applicants 
            WHERE term ILIKE '%Fall 2026%'
              AND (status ILIKE '%accepted%' OR status ILIKE '%acceptance%')
              AND (degree ILIKE '%phd%' OR degree ILIKE '%ph.d%')
              AND program ILIKE '%Computer Science%'
              AND (
                    program ILIKE '%Georgetown%' OR
                    program ILIKE '%Massachusetts Institute of Technology%' OR
                    program ILIKE '%MIT%' OR
                    program ILIKE '%Stanford%' OR
                    program ILIKE '%Carnegie Mellon%' OR
                    program ILIKE '%CMU%'
              );
        """
    },
    "Q9": {
        "title": "Question 9: Fall 2026 PhD CS Acceptances (LLM Fields)",
        "sql": """
            SELECT COUNT(*) FROM applicants 
            WHERE term ILIKE '%Fall 2026%'
              AND (status ILIKE '%accepted%' OR status ILIKE '%acceptance%')
              AND (degree ILIKE '%phd%' OR degree ILIKE '%ph.d%')
              AND llm_generated_program ILIKE '%Computer Science%'
              AND (
                    llm_generated_university ILIKE '%Georgetown%' OR
                    llm_generated_university ILIKE '%Massachusetts Institute of Technology%' OR
                    llm_generated_university ILIKE '%MIT%' OR
                    llm_generated_university ILIKE '%Stanford%' OR
                    llm_generated_university ILIKE '%Carnegie Mellon%' OR
                    llm_generated_university ILIKE '%CMU%'
              );
        """
    },
    "Q10": {
        "title": "Original Question 1: Average GPA by Degree Type (PhD vs Masters)",
        "sql": """
            SELECT 
                AVG(CASE WHEN degree ILIKE '%phd%' OR degree ILIKE '%ph.d%' THEN gpa END) AS avg_phd_gpa,
                AVG(CASE WHEN degree ILIKE '%master%' OR degree ILIKE '%ms%' THEN gpa END) AS avg_ms_gpa
            FROM applicants;
        """
    },
    "Q11": {
        "title": "Original Question 2: Acceptance Rate for Applicants with GPA >= 3.8 vs < 3.8",
        "sql": """
            SELECT 
                COUNT(*) FILTER (WHERE gpa >= 3.8 AND (status ILIKE '%accepted%' OR status ILIKE '%acceptance%')) * 100.0 / 
                NULLIF(COUNT(*) FILTER (WHERE gpa >= 3.8), 0) AS high_gpa_acceptance_pct,
                COUNT(*) FILTER (WHERE gpa < 3.8 AND (status ILIKE '%accepted%' OR status ILIKE '%acceptance%')) * 100.0 / 
                NULLIF(COUNT(*) FILTER (WHERE gpa < 3.8), 0) AS lower_gpa_acceptance_pct
            FROM applicants WHERE gpa IS NOT NULL;
        """
    }
}

def run_queries():
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            # Q1
            cur.execute(QUERIES["Q1"]["sql"])
            q1 = cur.fetchone()[0]
            print(f"Fall 2026 applicant count: {q1:,}")

            # Q2
            cur.execute(QUERIES["Q2"]["sql"])
            q2 = cur.fetchone()[0]
            print(f"Percent international: {q2:.2f}%" if q2 is not None else "Percent international: 0.00%")

            # Q3
            cur.execute(QUERIES["Q3"]["sql"])
            gpa, gre_q, gre_v, gre_aw = cur.fetchone()
            print(f"Average GPA: {gpa:.2f}" if gpa else "Average GPA: N/A")
            print(f"Average GRE Quantitative: {gre_q:.2f}" if gre_q else "Average GRE Quantitative: N/A")
            print(f"Average GRE Verbal: {gre_v:.2f}" if gre_v else "Average GRE Verbal: N/A")
            print(f"Average GRE Analytical Writing: {gre_aw:.2f}" if gre_aw else "Average GRE Analytical Writing: N/A")

            # Q4
            cur.execute(QUERIES["Q4"]["sql"])
            q4 = cur.fetchone()[0]
            print(f"Average GPA American Fall 2026: {q4:.2f}" if q4 else "Average GPA American Fall 2026: N/A")

            # Q5
            cur.execute(QUERIES["Q5"]["sql"])
            q5 = cur.fetchone()[0]
            print(f"Fall 2025 acceptance percentage: {q5:.2f}%" if q5 is not None else "Fall 2025 acceptance percentage: 0.00%")

            # Q6
            cur.execute(QUERIES["Q6"]["sql"])
            q6 = cur.fetchone()[0]
            print(f"Average GPA Accepted Fall 2026: {q6:.2f}" if q6 else "Average GPA Accepted Fall 2026: N/A")

            # Q7
            cur.execute(QUERIES["Q7"]["sql"])
            q7 = cur.fetchone()[0]
            print(f"JHU Masters Computer Science count: {q7:,}")

            # Q8
            cur.execute(QUERIES["Q8"]["sql"])
            q8 = cur.fetchone()[0]
            print(f"Original-field count: {q8:,}")

            # Q9
            cur.execute(QUERIES["Q9"]["sql"])
            q9 = cur.fetchone()[0]
            diff = q9 - q8
            print(f"LLM-field count: {q9:,}")
            print(f"Difference: {diff:+d}")

            # Q10 (Custom 1)
            cur.execute(QUERIES["Q10"]["sql"])
            phd_gpa, ms_gpa = cur.fetchone()
            print(f"Original Q1 - Avg PhD GPA: {phd_gpa:.2f} | Avg MS GPA: {ms_gpa:.2f}")

            # Q11 (Custom 2)
            cur.execute(QUERIES["Q11"]["sql"])
            high_acc, low_acc = cur.fetchone()
            print(f"Original Q2 - Acceptance (GPA >= 3.8): {high_acc:.2f}% | Acceptance (GPA < 3.8): {low_acc:.2f}%")

if __name__ == "__main__":
    run_queries()