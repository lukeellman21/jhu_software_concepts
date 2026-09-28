"""Button endpoints and busy-state gating.

Marker: ``buttons``.  The pipeline's busy flag lives on
:class:`src.flask_app.PullState`, so these tests set and read it directly
instead of waiting on a real background pull -- no ``sleep()`` anywhere.
"""
from __future__ import annotations

import pytest
from bs4 import BeautifulSoup

from helpers import Recorder
from src import flask_app

pytestmark = pytest.mark.buttons


def test_pull_data_returns_200_and_triggers_the_loader(stub_client, stub_services, records):
    """``POST /pull-data`` reports success and hands the scraped rows to the loader."""
    response = stub_client.post("/pull-data")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["busy"] is False
    assert payload["rows_loaded"] == len(records)

    assert stub_services["scraper"].call_count == 1
    assert stub_services["loader"].call_count == 1
    assert stub_services["loader"].calls[0][0][0] == records


def test_pull_data_records_completion_on_the_state(stub_app, records):
    """A successful pull timestamps the state and clears the busy flag."""
    state = stub_app.extensions[flask_app.EXTENSION_KEY]["state"]

    stub_app.test_client().post("/pull-data")

    assert state.busy is False
    assert state.rows_loaded == len(records)
    assert state.last_pull is not None
    assert state.error is None
    assert str(len(records)) in state.message


def test_update_analysis_returns_200_when_not_busy(stub_client, stub_services):
    """``POST /update-analysis`` recomputes the analysis and reports the keys."""
    response = stub_client.post("/update-analysis")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["updated_at"] is not None
    assert "percent_international" in payload["keys"]
    assert stub_services["analysis_provider"].call_count == 1


def test_update_analysis_refreshes_the_snapshot(stub_app, stub_services):
    """The recomputed analysis replaces the cached snapshot on the state."""
    state = stub_app.extensions[flask_app.EXTENSION_KEY]["state"]
    client = stub_app.test_client()

    client.post("/update-analysis")
    first = state.last_analysis_at
    client.post("/update-analysis")

    assert stub_services["analysis_provider"].call_count == 2
    assert state.analysis is not None
    assert first is not None


def test_update_analysis_is_gated_while_a_pull_is_in_progress(stub_app, stub_services):
    """While busy, ``/update-analysis`` answers 409 and performs no update."""
    state = stub_app.extensions[flask_app.EXTENSION_KEY]["state"]
    state.begin_pull()

    response = stub_app.test_client().post("/update-analysis")

    assert response.status_code == 409
    assert response.get_json()["busy"] is True
    assert stub_services["analysis_provider"].call_count == 0
    assert state.analysis is None
    assert state.last_analysis_at is None


def test_pull_data_is_gated_while_a_pull_is_in_progress(stub_app, stub_services):
    """A second ``/pull-data`` while busy answers 409 and scrapes nothing."""
    state = stub_app.extensions[flask_app.EXTENSION_KEY]["state"]
    state.begin_pull()

    response = stub_app.test_client().post("/pull-data")

    assert response.status_code == 409
    assert response.get_json() == {
        "ok": False,
        "busy": True,
        "message": "Pull in progress...",
    }
    assert stub_services["scraper"].call_count == 0
    assert stub_services["loader"].call_count == 0


def test_status_reports_the_busy_flag(stub_app):
    """The busy state is observable over HTTP, which is what the UI polls."""
    state = stub_app.extensions[flask_app.EXTENSION_KEY]["state"]
    client = stub_app.test_client()

    assert client.get("/status").get_json()["busy"] is False
    state.begin_pull()
    assert client.get("/status").get_json()["busy"] is True


def test_buttons_are_disabled_while_busy(stub_app):
    """The rendered buttons are disabled during a pull."""
    state = stub_app.extensions[flask_app.EXTENSION_KEY]["state"]
    state.begin_pull()

    page = BeautifulSoup(
        stub_app.test_client().get("/analysis").get_data(as_text=True), "html.parser"
    )

    assert page.find(attrs={"data-testid": flask_app.PULL_BUTTON_TESTID}).has_attr("disabled")
    assert page.find(attrs={"data-testid": flask_app.UPDATE_BUTTON_TESTID}).has_attr("disabled")


def test_pull_data_returns_500_when_the_loader_fails(make_app, stub_services):
    """A loader failure yields a non-200 response and a recorded error."""
    stub_services["loader"] = Recorder(error=RuntimeError("database is down"))
    app = make_app(**stub_services)
    state = app.extensions[flask_app.EXTENSION_KEY]["state"]

    response = app.test_client().post("/pull-data")

    assert response.status_code == 500
    payload = response.get_json()
    assert payload["ok"] is False
    assert payload["error"] == "database is down"
    assert state.busy is False
    assert state.error == "database is down"
    assert state.rows_loaded == 0


def test_pull_data_returns_202_for_a_background_runner(make_app, stub_services, records):
    """A background runner answers 202; the test joins the thread, it never sleeps."""
    threads = []

    def capturing_runner(job):
        thread = flask_app.run_in_thread(job)
        threads.append(thread)
        return thread

    app = make_app(runner=capturing_runner, **stub_services)
    state = app.extensions[flask_app.EXTENSION_KEY]["state"]

    response = app.test_client().post("/pull-data")

    assert response.status_code == 202
    assert response.get_json() == {
        "ok": True,
        "accepted": True,
        "message": "Pull started.",
    }

    threads[0].join(timeout=5)
    assert threads[0].is_alive() is False
    assert state.busy is False
    assert state.rows_loaded == len(records)


def test_run_sync_executes_the_job_inline():
    """The default runner runs the job and reports no background handle."""
    job = Recorder()
    assert flask_app.run_sync(job) is None
    assert job.call_count == 1


def test_run_in_thread_executes_the_job_on_a_thread():
    """The background runner returns a joinable thread."""
    job = Recorder()
    thread = flask_app.run_in_thread(job)
    thread.join(timeout=5)

    assert job.call_count == 1
    assert thread.daemon is True


class TestPullState:
    """Unit tests for the observable pipeline state."""

    def test_starts_idle(self):
        state = flask_app.PullState()
        assert state.snapshot() == {
            "busy": False,
            "message": "Idle",
            "error": None,
            "last_pull": None,
            "last_analysis_at": None,
            "rows_loaded": 0,
            "analysis_ready": False,
        }

    def test_begin_pull_sets_busy_and_clears_the_error(self):
        state = flask_app.PullState()
        state.fail_pull(RuntimeError("earlier failure"))
        state.begin_pull()

        assert state.busy is True
        assert state.error is None
        assert state.message == "Pull in progress..."

    def test_complete_pull_records_the_row_count(self):
        state = flask_app.PullState()
        state.begin_pull()
        state.complete_pull(7)

        assert state.busy is False
        assert state.rows_loaded == 7
        assert "7 new row(s)" in state.message
        assert state.snapshot()["last_pull"] == state.last_pull

    def test_fail_pull_records_the_error(self):
        state = flask_app.PullState()
        state.begin_pull()
        state.fail_pull(ValueError("bad row"))

        assert state.busy is False
        assert state.error == "bad row"
        assert state.message == "Pull failed: bad row"

    def test_record_analysis_stores_the_snapshot(self):
        state = flask_app.PullState()
        state.record_analysis({"total_applicants": 3})

        assert state.analysis == {"total_applicants": 3}
        assert state.last_analysis_at is not None
        assert state.snapshot()["analysis_ready"] is True
