from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

def build_limitations_pdf(filename="limitations.pdf"):
    doc = SimpleDocTemplate(
        filename,
        pagesize=letter,
        rightMargin=48,
        leftMargin=48,
        topMargin=48,
        bottomMargin=48
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
    heading_style = ParagraphStyle(
        'SectionHeading',
        parent=styles['Heading2'],
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#2B6CB0"),
        spaceBefore=10,
        spaceAfter=4,
        fontName="Helvetica-Bold"
    )
    body_style = ParagraphStyle(
        'BodyDark',
        parent=styles['Normal'],
        fontSize=9.5,
        leading=13.5,
        textColor=colors.HexColor("#2D3748"),
        spaceAfter=8
    )

    story = [
        Paragraph("GradCafé Pipeline Limitations & Architectural Reflection", title_style),
        Paragraph("Module 3 Analysis Deliverable | Data Engineering, Schema Constraints, and Scraping Vulnerabilities", subtitle_style),
        Spacer(1, 8),

        Paragraph("1. Web Scraping & Ingestion Brittleness", heading_style),
        Paragraph("Relying on HTML scraping from platforms like The Grad Café introduces severe structural vulnerabilities. Any front-end template redesign, dynamic DOM manipulation via JavaScript, or rate-limiting changes directly breaks parser selectors. In Module 2, unstructured string formatting led to significant field blending—such as degrees being concatenated directly into program titles ('Physics PhD'). Without strict upstream structural guarantees, scrapers require continuous heuristic regular expressions to clean incoming records.", body_style),

        Paragraph("2. Database Constraints & Entity Disambiguation", heading_style),
        Paragraph("A single-table relational schema (`applicants`) enforces atomicity at the row level but fails to normalize institutional and academic relationships. Universities, degree levels, and programs should be separated into relational entities linked via foreign keys. Because admissions entries are user-submitted, variations like 'MIT', 'Mass Tech', and 'Massachusetts Institute of Technology' represent identical institutions but evaluate differently in basic SQL ILIKE queries unless LLM-assisted normalization or canonical lookup tables are applied.", body_style),

        Paragraph("3. LLM Field Reliability vs. Deterministic Parsing", heading_style),
        Paragraph("While zero-shot LLM prompts resolve complex, unstandardized text variations, they introduce non-deterministic latencies and minor hallucination risks. When normalizing 30,000+ records, LLM parsing costs and throughput constraints necessitate asynchronous batching or fallback rules. The LLM fields proved critical for disambiguating university names where standard regex patterns failed, but strict JSON schema validation is mandatory before writing predictions directly into relational tables.", body_style),

        Paragraph("4. Architectural Scalability & Background Workflows", heading_style),
        Paragraph("Triggering heavy ingestion or statistical recalculations inside synchronous HTTP request-response cycles risks blocking the web server and dropping client connections. In our Flask implementation, lightweight threading isolates worker routines from the web interface. In a full production deployment, this architecture should be decoupled using dedicated task queues like Celery or Redis Queue (RQ) backed by an independent worker fleet, guaranteeing transactional retries and worker fault tolerance.", body_style)
    ]

    doc.build(story)
    print(f"Generated {filename} successfully.")

if __name__ == "__main__":
    build_limitations_pdf()