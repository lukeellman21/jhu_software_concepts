import os
import psycopg
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost/gradcafe")

def get_query_data():
    results = []
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            # Q1
            cur.execute("SELECT COUNT(*) FROM applicants WHERE term ILIKE '%Fall 2026%';")
            q1 = cur.fetchone()[0]
            results.append(("1", "Fall 2026 Applicants Count", f"{q1:,}"))

            # Q2
            cur.execute("""
                SELECT COUNT(*) FILTER (WHERE us_or_international ILIKE 'international') * 100.0 / 
                       NULLIF(COUNT(*) FILTER (WHERE us_or_international IS NOT NULL AND TRIM(us_or_international) <> ''), 0)
                FROM applicants;
            """)
            q2 = cur.fetchone()[0]
            results.append(("2", "Percent International Applicants", f"{q2:.2f}%" if q2 is not None else "0.00%"))

            # Q3
            cur.execute("SELECT AVG(gpa), AVG(gre), AVG(gre_v), AVG(gre_aw) FROM applicants;")
            gpa, gre_q, gre_v, gre_aw = cur.fetchone()
            q3_text = f"GPA: {gpa:.2f} | GRE Q: {gre_q:.2f} | GRE V: {gre_v:.2f} | GRE AW: {gre_aw:.2f}"
            results.append(("3", "Average Metrics (Overall GPA and GRE)", q3_text))

            # Q4
            cur.execute("""
                SELECT AVG(gpa) FROM applicants 
                WHERE term ILIKE '%Fall 2026%' AND us_or_international ILIKE 'american' AND gpa IS NOT NULL;
            """)
            q4 = cur.fetchone()[0]
            results.append(("4", "Average GPA of Fall 2026 American Applicants", f"{q4:.2f}" if q4 is not None else "N/A"))

            # Q5
            cur.execute("""
                SELECT COUNT(*) FILTER (WHERE status ILIKE '%accepted%' OR status ILIKE '%acceptance%') * 100.0 / NULLIF(COUNT(*), 0)
                FROM applicants WHERE term ILIKE '%Fall 2025%';
            """)
            q5 = cur.fetchone()[0]
            results.append(("5", "Fall 2025 Acceptance Percentage", f"{q5:.2f}%" if q5 is not None else "0.00%"))

            # Q6
            cur.execute("""
                SELECT AVG(gpa) FROM applicants 
                WHERE term ILIKE '%Fall 2026%' AND (status ILIKE '%accepted%' OR status ILIKE '%acceptance%') AND gpa IS NOT NULL;
            """)
            q6 = cur.fetchone()[0]
            results.append(("6", "Average GPA of Accepted Fall 2026 Applicants", f"{q6:.2f}" if q6 is not None else "N/A"))

            # Q7
            cur.execute("""
                SELECT COUNT(*) FROM applicants 
                WHERE (program ILIKE '%Johns Hopkins%' OR program ILIKE '%JHU%')
                  AND program ILIKE '%Computer Science%'
                  AND (degree ILIKE '%master%' OR degree ILIKE '%MS%' OR degree ILIKE '%M.S.%');
            """)
            q7 = cur.fetchone()[0]
            results.append(("7", "JHU Master's in Computer Science Count", f"{q7:,}"))

            # Q8
            cur.execute("""
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
            """)
            q8 = cur.fetchone()[0]
            results.append(("8", "Fall 2026 PhD CS Acceptances (Original Fields)", f"{q8:,}"))

            # Q9
            cur.execute("""
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
            """)
            q9 = cur.fetchone()[0]
            diff = q9 - q8
            results.append(("9", "Fall 2026 PhD CS Acceptances (LLM Fields & Difference)", f"LLM: {q9:,} | Diff: {diff:+d}"))

            # Q10 (Custom 1)
            cur.execute("""
                SELECT 
                    AVG(CASE WHEN degree ILIKE '%phd%' OR degree ILIKE '%ph.d%' THEN gpa END) AS avg_phd_gpa,
                    AVG(CASE WHEN degree ILIKE '%master%' OR degree ILIKE '%ms%' THEN gpa END) AS avg_ms_gpa
                FROM applicants;
            """)
            phd_gpa, ms_gpa = cur.fetchone()
            results.append(("10", "Original Q1: Average GPA by Degree (PhD vs MS)", f"PhD: {phd_gpa:.2f} | MS: {ms_gpa:.2f}"))

            # Q11 (Custom 2)
            cur.execute("""
                SELECT 
                    COUNT(*) FILTER (WHERE gpa >= 3.8 AND (status ILIKE '%accepted%' OR status ILIKE '%acceptance%')) * 100.0 / 
                    NULLIF(COUNT(*) FILTER (WHERE gpa >= 3.8), 0) AS high_gpa_acc,
                    COUNT(*) FILTER (WHERE gpa < 3.8 AND (status ILIKE '%accepted%' OR status ILIKE '%acceptance%')) * 100.0 / 
                    NULLIF(COUNT(*) FILTER (WHERE gpa < 3.8), 0) AS low_gpa_acc
                FROM applicants WHERE gpa IS NOT NULL;
            """)
            high_acc, low_acc = cur.fetchone()
            results.append(("11", "Original Q2: Acceptance Rate (GPA >= 3.8 vs < 3.8)", f">= 3.8: {high_acc:.2f}% | < 3.8: {low_acc:.2f}%"))

    return results

def create_pdf(filename="query_results.pdf"):
    doc = SimpleDocTemplate(
        filename,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#1A365D"),
        spaceAfter=6
    )
    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#4A5568"),
        spaceAfter=14
    )
    cell_style = ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#2D3748")
    )
    header_style = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontSize=9,
        leading=12,
        textColor=colors.white,
        fontName="Helvetica-Bold"
    )

    story = [
        Paragraph("Grad Café Analysis: Query Results", title_style),
        Paragraph("Module 3 Deliverable | Database Queries and Statistical Summary", subtitle_style),
        Spacer(1, 10)
    ]

    data = [[
        Paragraph("#", header_style),
        Paragraph("Analysis Question", header_style),
        Paragraph("Result / Metric", header_style)
    ]]

    for q_num, question, result in get_query_data():
        data.append([
            Paragraph(q_num, cell_style),
            Paragraph(question, cell_style),
            Paragraph(result, cell_style)
        ])

    table = Table(data, colWidths=[28, 330, 180])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1A365D")),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7FAFC")]),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))

    story.append(table)
    doc.build(story)
    print(f"Generated {filename} successfully.")

if __name__ == "__main__":
    create_pdf()