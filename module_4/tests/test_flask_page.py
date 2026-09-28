"""Flask application factory, routing and analysis-page rendering.

Marker: ``web``.
"""
from __future__ import annotations

import pytest
from bs4 import BeautifulSoup

from helpers import Recorder
from src import flask_app, query_data

pytestmark = pytest.mark.web

REQUIRED_ROUTES = {
    "/": {"GET"},
    "/analysis": {"GET"},
    "/pull-data": {"POST"},
    "/update-analysis": {"POST"},
    "/status": {"GET"},
}


def soup_of(response):
    """Parse a Flask response body with BeautifulSoup."""
    return BeautifulSoup(response.get_data(as_text=True), "html.parser")


def test_create_app_returns_a_testable_app(make_app):
    """The factory produces an app in testing mode with its services wired."""
    app = make_app()

    assert isinstance(app, flask_app.Flask)
    assert app.config["TESTING"] is True
    services = app.extensions[flask_app.EXTENSION_KEY]
    assert set(services) == {"state", "scraper", "loader", "analysis", "rows", "runner"}
    assert isinstance(services["state"], flask_app.PullState)
    assert services["runner"] is flask_app.run_sync


def test_create_app_honours_configured_database_url(make_app):
    """A ``DATABASE_URL`` passed through ``config`` reaches ``app.config``."""
    app = make_app(config={"DATABASE_URL": "postgresql://localhost/somewhere_else"})
    assert app.config["DATABASE_URL"] == "postgresql://localhost/somewhere_else"


def test_create_app_falls_back_to_environment_database_url(monkeypatch):
    """With no explicit config the factory reads ``DATABASE_URL`` from the environment."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/from_env")
    app = flask_app.create_app()
    assert app.config["DATABASE_URL"] == "postgresql://localhost/from_env"


@pytest.mark.parametrize("rule, methods", sorted(REQUIRED_ROUTES.items()))
def test_required_routes_are_registered(stub_app, rule, methods):
    """Every route the UI and the tests depend on exists with the right method."""
    registered = {r.rule: r.methods for r in stub_app.url_map.iter_rules()}
    assert rule in registered
    assert methods <= registered[rule]


def test_home_redirects_to_the_analysis_page(stub_client):
    """``GET /`` sends the visitor to ``/analysis``."""
    response = stub_client.get("/")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/analysis")

    followed = stub_client.get("/", follow_redirects=True)
    assert followed.status_code == 200


def test_analysis_page_loads(stub_client):
    """``GET /analysis`` returns 200."""
    assert stub_client.get("/analysis").status_code == 200


def test_analysis_page_renders_required_components(stub_client):
    """The page shows the word Analysis, both buttons and at least one answer."""
    text = stub_client.get("/analysis").get_data(as_text=True)

    assert "Analysis" in text
    assert "Pull Data" in text
    assert "Update Analysis" in text
    assert text.count("Answer:") >= 1


def test_analysis_page_exposes_stable_selectors(stub_client):
    """Both buttons carry the agreed ``data-testid`` hooks."""
    page = soup_of(stub_client.get("/analysis"))

    pull = page.find(attrs={"data-testid": flask_app.PULL_BUTTON_TESTID})
    update = page.find(attrs={"data-testid": flask_app.UPDATE_BUTTON_TESTID})

    assert pull is not None and pull.name == "button"
    assert update is not None and update.name == "button"
    assert pull.get_text(strip=True) == "Pull Data"
    assert update.get_text(strip=True) == "Update Analysis"


def test_analysis_page_posts_to_the_button_endpoints(stub_client):
    """Each button sits in a form that posts to its own endpoint."""
    page = soup_of(stub_client.get("/analysis"))

    pull_form = page.find("form", id="pull-data-form")
    update_form = page.find("form", id="update-analysis-form")

    assert pull_form["action"] == "/pull-data"
    assert pull_form["method"].upper() == "POST"
    assert update_form["action"] == "/update-analysis"
    assert update_form["method"].upper() == "POST"


def test_analysis_page_renders_one_item_per_question(stub_client):
    """There is exactly one labelled answer per declared analysis question."""
    page = soup_of(stub_client.get("/analysis"))
    items = page.find_all(attrs={"data-testid": "analysis-item"})

    assert len(items) == len(query_data.EXPECTED_KEYS)
    assert {item["data-key"] for item in items} == set(query_data.EXPECTED_KEYS)


def test_analysis_is_computed_once_and_then_cached(stub_app, stub_services):
    """The first page view computes the analysis; later views reuse the snapshot."""
    client = stub_app.test_client()

    client.get("/analysis")
    client.get("/analysis")

    assert stub_services["analysis_provider"].call_count == 1


def test_analysis_page_renders_recent_rows(make_app, stub_services):
    """Rows returned by the query layer appear in the recent-entries table."""
    row = {key: None for key in query_data.ROW_KEYS}
    row.update(p_id=42, program="Johns Hopkins University - Computer Science", gpa=3.75)
    stub_services["rows_provider"] = Recorder(result=[row])
    app = make_app(**stub_services)

    page = soup_of(app.test_client().get("/analysis"))
    table = page.find(attrs={"data-testid": "recent-rows"}).get_text(" ", strip=True)

    assert "#42" in table
    assert "Johns Hopkins University - Computer Science" in table
    assert "3.75" in table


def test_analysis_page_reports_an_empty_table(stub_client):
    """With no rows loaded the table says so rather than rendering an empty body."""
    page = soup_of(stub_client.get("/analysis"))
    table = page.find(attrs={"data-testid": "recent-rows"}).get_text(" ", strip=True)

    assert "No applicant rows loaded yet." in table


def test_analysis_page_surfaces_a_failed_pull(stub_app):
    """A recorded pull error is shown to the operator."""
    state = stub_app.extensions[flask_app.EXTENSION_KEY]["state"]
    state.fail_pull(RuntimeError("loader exploded"))

    page = soup_of(stub_app.test_client().get("/analysis"))
    banner = page.find(attrs={"data-testid": "pull-error"})

    assert banner is not None
    assert "loader exploded" in banner.get_text()


def test_status_route_reports_an_idle_pipeline(stub_client):
    """``GET /status`` exposes the pipeline state as JSON."""
    payload = stub_client.get("/status").get_json()

    assert payload["busy"] is False
    assert payload["message"] == "Idle"
    assert payload["rows_loaded"] == 0


def test_service_accessors_resolve_against_the_active_app(stub_app):
    """``get_services`` and ``get_state`` read from the current application."""
    with stub_app.test_request_context("/analysis"):
        assert flask_app.get_services() is stub_app.extensions[flask_app.EXTENSION_KEY]
        assert flask_app.get_state() is stub_app.extensions[flask_app.EXTENSION_KEY]["state"]
