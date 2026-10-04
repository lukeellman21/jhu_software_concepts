"""End-to-end flows: pull -> update -> render, against a real database.

Marker: ``integration``.  The scraper is a test double returning several
records; everything downstream of it -- the loader, PostgreSQL, the query layer
and the rendered page -- is the real implementation.
"""
from __future__ import annotations

import re

import pytest
from bs4 import BeautifulSoup

from helpers import Recorder
from src import flask_app, load_data, query_data

pytestmark = pytest.mark.integration

PERCENT_PATTERN = re.compile(r"\d+(?:,\d{3})*(?:\.(\d+))?%")


def answer_for(response, key: str) -> str:
    """Return the rendered answer for one analysis key."""
    page = BeautifulSoup(response.get_data(as_text=True), "html.parser")
    item = page.find(attrs={"data-key": key})
    return item.find(attrs={"data-testid": "analysis-answer"}).get_text(strip=True)


def test_pull_then_update_then_render(client, conn, records, empty_db):
    """The full flow: an empty page, a pull, an update, then refreshed answers."""
    before = client.get("/analysis")
    assert before.status_code == 200
    assert answer_for(before, "total_applicants") == "Answer: 0"

    pull = client.post("/pull-data")
    assert pull.status_code == 200
    assert pull.get_json()["ok"] is True
    assert query_data.count_rows(conn=conn) == len(records)

    stale = client.get("/analysis")
    assert answer_for(stale, "total_applicants") == "Answer: 0"

    update = client.post("/update-analysis")
    assert update.status_code == 200

    after = client.get("/analysis")
    assert answer_for(after, "total_applicants") == f"Answer: {len(records)}"
    assert answer_for(after, "fall_2026_count") == "Answer: 2"


def test_rendered_values_are_formatted_after_a_real_pull(client, conn, empty_db):
    """Percentages computed from real rows still render with two decimals."""
    client.post("/pull-data")
    client.post("/update-analysis")
    response = client.get("/analysis")

    # One international entry out of three that declared an origin.
    assert answer_for(response, "percent_international") == "Answer: 33.33%"
    # Two acceptances out of four entries.
    assert answer_for(response, "overall_acceptance_percent") == "Answer: 50.00%"
    assert answer_for(response, "avg_gpa") == "Answer: 3.75"

    decimals = PERCENT_PATTERN.findall(response.get_data(as_text=True))
    assert decimals
    assert all(len(group) == 2 for group in decimals)


def test_loaded_rows_appear_in_the_recent_entries_table(client, conn, empty_db):
    """The page's row table is fed by the same database the pull wrote to."""
    client.post("/pull-data")
    page = BeautifulSoup(client.get("/analysis").get_data(as_text=True), "html.parser")
    table = page.find(attrs={"data-testid": "recent-rows"}).get_text(" ", strip=True)

    assert "#1000004" in table
    assert "Bennington College" in table


def test_multiple_pulls_with_overlapping_data_stay_consistent(
    make_app, conn, records, empty_db
):
    """Overlapping pulls insert only the records the database has not seen."""
    batches = [records[:3], records[1:]]
    scraper = Recorder(result=lambda: batches.pop(0))
    client = make_app(scraper=scraper).test_client()

    first = client.post("/pull-data").get_json()
    second = client.post("/pull-data").get_json()

    assert first["rows_loaded"] == 3
    assert second["rows_loaded"] == 1
    assert query_data.count_rows(conn=conn) == len(records)

    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(DISTINCT p_id) FROM applicants;")
        assert cur.fetchone()[0] == len(records)


def test_a_pull_in_progress_blocks_an_update_mid_flow(client, conn, state, records, empty_db):
    """A busy pipeline refuses to recompute, and the page keeps its old answers."""
    client.post("/pull-data")
    client.post("/update-analysis")
    assert answer_for(client.get("/analysis"), "total_applicants") == f"Answer: {len(records)}"

    load_data.insert_rows([{"url": "https://www.thegradcafe.com/result/2000001"}], conn=conn)
    state.begin_pull()

    blocked = client.post("/update-analysis")

    assert blocked.status_code == 409
    assert blocked.get_json()["busy"] is True
    assert answer_for(client.get("/analysis"), "total_applicants") == f"Answer: {len(records)}"


def test_a_failing_loader_leaves_the_database_untouched(make_app, conn, fake_scraper, empty_db):
    """An error part-way through the flow yields a 500 and no rows."""
    app = make_app(
        scraper=fake_scraper,
        loader=Recorder(error=RuntimeError("connection refused")),
    )

    response = app.test_client().post("/pull-data")

    assert response.status_code == 500
    assert query_data.count_rows(conn=conn) == 0
    assert app.extensions[flask_app.EXTENSION_KEY]["state"].error == "connection refused"
