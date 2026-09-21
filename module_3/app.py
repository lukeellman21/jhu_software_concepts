import os
import threading
import time
from flask import Flask, render_template, request, redirect, url_for, flash
from sqlalchemy import select, func, and_, or_, desc
from models import get_db_session, Applicant

app = Flask(__name__)
app.secret_key = "gradcafe-secret-key"

# In-memory status for background tasks
task_status = {
    "pull_data": {"running": False, "last_run": None, "message": "Idle"},
    "update_analysis": {"running": False, "last_run": None, "message": "Idle"}
}

def mock_pull_data():
    task_status["pull_data"]["running"] = True
    task_status["pull_data"]["message"] = "Scraping latest entries in background..."
    # Simulates background non-blocking scrape worker
    time.sleep(4)
    task_status["pull_data"]["running"] = False
    task_status["pull_data"]["last_run"] = time.strftime("%Y-%m-%d %H:%M:%S")
    task_status["pull_data"]["message"] = f"Completed background pull at {task_status['pull_data']['last_run']}"

def mock_update_analysis():
    task_status["update_analysis"]["running"] = True
    task_status["update_analysis"]["message"] = "Recalculating statistics..."
    time.sleep(2)
    task_status["update_analysis"]["running"] = False
    task_status["update_analysis"]["last_run"] = time.strftime("%Y-%m-%d %H:%M:%S")
    task_status["update_analysis"]["message"] = f"Analysis updated at {task_status['update_analysis']['last_run']}"

@app.route("/")
def index():
    session = get_db_session()
    try:
        # 1. Total Applicants
        total_applicants = session.execute(select(func.count(Applicant.p_id))).scalar() or 0

        # 2. Fall 2026 Applicants
        fall_2026_count = session.execute(
            select(func.count(Applicant.p_id)).where(Applicant.term.ilike("%Fall 2026%"))
        ).scalar() or 0

        # 3. Overall Acceptance Rate
        accepted_cnt = session.execute(
            select(func.count(Applicant.p_id)).where(
                or_(Applicant.status.ilike("%accepted%"), Applicant.status.ilike("%acceptance%"))
            )
        ).scalar() or 0
        acceptance_rate = (accepted_cnt * 100.0 / total_applicants) if total_applicants > 0 else 0.0

        # 4. Average GPA
        avg_gpa = session.execute(
            select(func.avg(Applicant.gpa)).where(Applicant.gpa.is_not(None))
        ).scalar() or 0.0

        # 5. Search & Pagination for data table
        search_query = request.args.get("q", "").strip()
        page = request.args.get("page", 1, type=int)
        per_page = 20

        base_stmt = select(Applicant)
        if search_query:
            base_stmt = base_stmt.where(
                or_(
                    Applicant.program.ilike(f"%{search_query}%"),
                    Applicant.status.ilike(f"%{search_query}%"),
                    Applicant.degree.ilike(f"%{search_query}%"),
                    Applicant.term.ilike(f"%{search_query}%")
                )
            )

        total_matching = session.execute(
            select(func.count()).select_from(base_stmt.subquery())
        ).scalar() or 0

        records = session.execute(
            base_stmt.order_by(desc(Applicant.p_id)).offset((page - 1) * per_page).limit(per_page)
        ).scalars().all()

        total_pages = max(1, (total_matching + per_page - 1) // per_page)

        metrics = {
            "total_applicants": total_applicants,
            "fall_2026_count": fall_2026_count,
            "acceptance_rate": f"{acceptance_rate:.2f}%",
            "avg_gpa": f"{avg_gpa:.2f}"
        }

        return render_template(
            "index.html",
            metrics=metrics,
            records=records,
            page=page,
            total_pages=total_pages,
            search_query=search_query,
            task_status=task_status
        )
    finally:
        session.close()

@app.route("/trigger-pull", methods=["POST"])
def trigger_pull():
    if not task_status["pull_data"]["running"]:
        thread = threading.Thread(target=mock_pull_data)
        thread.daemon = True
        thread.start()
        flash("Background scrape job started successfully.")
    else:
        flash("Scrape job is already running.")
    return redirect(url_for("index"))

@app.route("/trigger-analysis", methods=["POST"])
def trigger_analysis():
    if not task_status["update_analysis"]["running"]:
        thread = threading.Thread(target=mock_update_analysis)
        thread.daemon = True
        thread.start()
        flash("Analysis update job initiated.")
    else:
        flash("Analysis update is currently executing.")
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(debug=True, port=5000)