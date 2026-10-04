"""Web layer: the Flask application factory and its routes.

The factory takes the scraper, the loader, the analysis provider and the job
runner as arguments, so the test suite can inject fakes and never touch the
network.  Pipeline state is held in a single :class:`PullState` object that the
tests can read and write directly -- busy-state behaviour is therefore
observable and injectable rather than timing dependent.

Routes
------
``GET /``
    Redirect to ``/analysis``.
``GET /analysis``
    The analysis page: both buttons plus one ``Answer:`` per question.
``POST /pull-data``
    Scrape and load new rows.  ``200 {"ok": true}`` when it ran,
    ``202`` when handed to a background runner, ``409 {"busy": true}`` when a
    pull is already in progress, ``500 {"ok": false}`` when the loader failed.
``POST /update-analysis``
    Recompute the analysis.  ``200 {"ok": true}``, or ``409 {"busy": true}``
    while a pull is in progress (in which case nothing is recomputed).
``GET /status``
    JSON snapshot of :class:`PullState`, used by the page and by tests.
"""
from __future__ import annotations

import os
import secrets
import threading
from datetime import datetime, timezone
from functools import partial
from typing import Any, Callable, Dict, Optional

import psycopg
from flask import (Blueprint, Flask, current_app, jsonify, redirect,
                   render_template, request, url_for)

from . import db, load_data, query_data, scrape

#: Key under which the service bundle is stored in ``app.extensions``.
EXTENSION_KEY = "gradcafe"

#: ``data-testid`` values the UI tests rely on; they must match the literals in
#: ``templates/analysis.html`` (the page tests fail if they drift apart).
PULL_BUTTON_TESTID = "pull-data-btn"
UPDATE_BUTTON_TESTID = "update-analysis-btn"

#: Shown on the page when PostgreSQL cannot be reached, instead of a 500.
DATABASE_UNAVAILABLE_MESSAGE = (
    "The analysis database is unreachable, so the answers below are unavailable. "
    "Check that PostgreSQL is running (`pg_isready`) and that DATABASE_URL points "
    "at an existing database, then reload this page."
)

bp = Blueprint("gradcafe", __name__)


def _now() -> str:
    """Return the current UTC time as a second-precision ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class PullState:
    """Observable state of the data pipeline.

    A single instance lives on the application; tests may flip
    :attr:`busy` directly to simulate a pull that is in progress, which keeps
    busy-state tests free of sleeps and threads.
    """

    def __init__(self) -> None:
        self.busy = False
        self.message = "Idle"
        self.error: Optional[str] = None
        self.last_pull: Optional[str] = None
        self.last_analysis_at: Optional[str] = None
        self.rows_loaded = 0
        self.analysis: Optional[Dict[str, Any]] = None

    def begin_pull(self) -> None:
        """Mark a pull as in progress."""
        self.busy = True
        self.error = None
        self.message = "Pull in progress..."

    def complete_pull(self, rows_loaded: int) -> None:
        """Mark a pull as finished successfully."""
        self.busy = False
        self.rows_loaded = rows_loaded
        self.last_pull = _now()
        self.message = f"Loaded {rows_loaded} new row(s) at {self.last_pull}"

    def fail_pull(self, error: BaseException) -> None:
        """Mark a pull as finished with an error."""
        self.busy = False
        self.error = str(error)
        self.message = f"Pull failed: {self.error}"

    def record_analysis(self, analysis: Dict[str, Any]) -> None:
        """Store a freshly computed analysis snapshot."""
        self.analysis = analysis
        self.last_analysis_at = _now()

    def snapshot(self) -> Dict[str, Any]:
        """Return a JSON-serialisable view of the state."""
        return {
            "busy": self.busy,
            "message": self.message,
            "error": self.error,
            "last_pull": self.last_pull,
            "last_analysis_at": self.last_analysis_at,
            "rows_loaded": self.rows_loaded,
            "analysis_ready": self.analysis is not None,
        }


def run_sync(job: Callable[[], None]) -> None:
    """Default runner: execute ``job`` inline.

    Returns ``None``, which is how :func:`pull_data` knows the job already ran
    rather than being handed to a background worker.
    """
    job()


def run_in_thread(job: Callable[[], None]) -> threading.Thread:
    """Alternative runner: execute ``job`` on a daemon thread.

    Returning the thread tells the route to answer ``202 Accepted``; the caller
    (or a test) can join the returned thread instead of sleeping.
    """
    thread = threading.Thread(target=job, daemon=True)
    thread.start()
    return thread


def get_services() -> Dict[str, Any]:
    """Return the injected service bundle for the active application."""
    return current_app.extensions[EXTENSION_KEY]


def get_state() -> PullState:
    """Return the :class:`PullState` of the active application."""
    return get_services()["state"]


@bp.get("/")
def home():
    """Redirect the site root to the analysis page."""
    return redirect(url_for("gradcafe.analysis_page"))


def read_row_options() -> Dict[str, Any]:
    """Read and validate the recent-rows query parameters.

    Nothing read here reaches SQL as text.  ``limit`` is clamped to
    :data:`src.query_data.MIN_LIMIT`..:data:`src.query_data.MAX_LIMIT`, ``sort``
    is checked against the :data:`src.query_data.ROW_KEYS` allow-list, and
    ``q`` is bound as a query parameter by
    :func:`src.query_data.build_rows_statement`.

    :returns: ``{"limit", "sort_by", "descending", "search"}``.
    """
    sort_by = request.args.get("sort", "p_id")
    return {
        "limit": query_data.clamp_limit(request.args.get("limit")),
        "sort_by": sort_by if sort_by in query_data.ROW_KEYS else "p_id",
        "descending": request.args.get("dir", "desc").lower() != "asc",
        "search": (request.args.get("q") or "").strip(),
    }


@bp.get("/analysis")
def analysis_page():
    """Render the analysis page.

    The page renders the cached analysis snapshot, computing one on first visit
    so a fresh application is never blank.  ``POST /update-analysis`` refreshes
    the snapshot.

    If PostgreSQL cannot be reached the page still renders, with every answer
    blank and a banner explaining the problem, rather than failing with a 500.
    """
    services = get_services()
    state = services["state"]
    options = read_row_options()
    database_error = None

    try:
        if state.analysis is None:
            state.record_analysis(services["analysis"]())
        rows = services["rows"](**options)
    except psycopg.OperationalError as exc:
        current_app.logger.warning("Analysis page degraded: %s", exc)
        database_error = DATABASE_UNAVAILABLE_MESSAGE
        rows = []

    analysis = state.analysis or {}
    return render_template(
        "analysis.html",
        items=query_data.get_analysis_items(analysis),
        analysis=analysis,
        rows=rows,
        options=options,
        sortable=query_data.ROW_KEYS,
        max_limit=query_data.MAX_LIMIT,
        state=state.snapshot(),
        database_error=database_error,
    )


@bp.post("/pull-data")
def pull_data():
    """Scrape new Grad Café rows and load them into PostgreSQL."""
    services = get_services()
    state: PullState = services["state"]

    if state.busy:
        return jsonify({"ok": False, "busy": True, "message": state.message}), 409

    state.begin_pull()
    outcome: Dict[str, Any] = {}

    def job() -> None:
        try:
            records = services["scraper"]()
            outcome["rows_loaded"] = services["loader"](records)
            state.complete_pull(outcome["rows_loaded"])
        except (psycopg.Error, OSError, ValueError, RuntimeError) as exc:
            # Any failure in the scraper or loader is reported as a 500 rather
            # than escaping as an unhandled exception.
            outcome["error"] = str(exc)
            state.fail_pull(exc)

    handle = services["runner"](job)
    if handle is not None:
        # A background runner owns the job now, so the response reports the
        # hand-off rather than a state that is still being written to.
        return jsonify({"ok": True, "accepted": True, "message": "Pull started."}), 202
    if "error" in outcome:
        return jsonify({"ok": False, "busy": False, "error": outcome["error"]}), 500
    return (
        jsonify(
            {
                "ok": True,
                "busy": False,
                "rows_loaded": outcome["rows_loaded"],
                "message": state.message,
            }
        ),
        200,
    )


@bp.post("/update-analysis")
def update_analysis():
    """Recompute the analysis snapshot, unless a pull is in progress."""
    services = get_services()
    state: PullState = services["state"]

    if state.busy:
        return jsonify({"ok": False, "busy": True, "message": state.message}), 409

    try:
        state.record_analysis(services["analysis"]())
    except psycopg.OperationalError as exc:
        return jsonify({"ok": False, "busy": False, "error": str(exc)}), 503

    return (
        jsonify(
            {
                "ok": True,
                "busy": False,
                "updated_at": state.last_analysis_at,
                "keys": sorted(state.analysis),
            }
        ),
        200,
    )


@bp.get("/status")
def status():
    """Return the pipeline state as JSON."""
    return jsonify(get_state().snapshot()), 200


#: Service names :func:`create_app` accepts overrides for.
SERVICE_NAMES = ("scraper", "loader", "analysis", "rows", "runner")


def default_services(database_url: str) -> Dict[str, Any]:
    """Return the production service bundle bound to a connection string.

    :param database_url: connection string the data services should use.
    :returns: mapping of :data:`SERVICE_NAMES` to callables.
    """
    return {
        "scraper": scrape.pull_new_records,
        "loader": partial(load_data.insert_rows, database_url=database_url),
        "analysis": partial(query_data.get_analysis, database_url=database_url),
        "rows": partial(query_data.get_recent_rows, database_url=database_url),
        "runner": run_sync,
    }


def create_app(
    config: Optional[Dict[str, Any]] = None,
    services: Optional[Dict[str, Any]] = None,
    state: Optional[PullState] = None,
) -> Flask:
    """Build and return a configured Flask application.

    Every external dependency is injectable, which is what lets the test suite
    swap in fakes without touching the network or a real browser.

    :param config: values merged into ``app.config``.  ``DATABASE_URL`` is
        honoured by the default data services.
    :param services: overrides for any of :data:`SERVICE_NAMES`:

        ``scraper``
            callable returning a list of raw records; defaults to
            :func:`src.scrape.pull_new_records`.
        ``loader``
            callable taking those records and returning the number of new rows;
            defaults to :func:`src.load_data.insert_rows`.
        ``analysis``
            callable returning the analysis dict; defaults to
            :func:`src.query_data.get_analysis`.
        ``rows``
            callable returning recent rows for the page table; defaults to
            :func:`src.query_data.get_recent_rows`.
        ``runner``
            callable that executes the pull job; defaults to :func:`run_sync`.
            Pass :func:`run_in_thread` for background pulls.

    :param state: pre-built :class:`PullState`, handy for seeding a busy state.
    :returns: the application, with the service bundle in
        ``app.extensions["gradcafe"]``.
    """
    app = Flask(__name__)
    app.config.update(
        # Never hard-coded: supplied by the environment in deployment, random
        # (and therefore per-process) otherwise.
        SECRET_KEY=os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32),
        DATABASE_URL=db.get_database_url(),
    )
    if config:
        app.config.update(config)

    bundle = default_services(app.config["DATABASE_URL"])
    bundle.update({k: v for k, v in (services or {}).items() if v is not None})
    bundle["state"] = state or PullState()

    app.extensions[EXTENSION_KEY] = bundle
    app.register_blueprint(bp)
    return app


if __name__ == "__main__":  # pragma: no cover - development server entry point
    create_app().run(port=5000)
