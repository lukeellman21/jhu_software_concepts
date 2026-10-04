"""Labels and rounding of the rendered analysis.

Marker: ``analysis``.  The contract is narrow and explicit: every analysis item
is labelled ``Answer:`` and every percentage is printed with exactly two
decimal places.
"""
from __future__ import annotations

import re

import pytest
from bs4 import BeautifulSoup

from src import query_data

pytestmark = pytest.mark.analysis

#: Matches any percentage on the page, capturing its decimal digits.
PERCENT_PATTERN = re.compile(r"\d+(?:,\d{3})*(?:\.(\d+))?%")


@pytest.mark.parametrize(
    "value, expected",
    [
        (39.283, "39.28%"),
        (39.286, "39.29%"),
        (0, "0.00%"),
        (None, "0.00%"),
        (100, "100.00%"),
        (33.333333, "33.33%"),
    ],
)
def test_format_percent_uses_two_decimals(value, expected):
    """Percentages are rounded to two decimals and always show both."""
    assert query_data.format_percent(value) == expected


@pytest.mark.parametrize(
    "value, expected",
    [(3.456, "3.46"), (3.0, "3.00"), (None, "N/A")],
)
def test_format_float_uses_two_decimals_or_na(value, expected):
    """Averages show two decimals, and missing data reads ``N/A``."""
    assert query_data.format_float(value) == expected


@pytest.mark.parametrize("value, expected", [(0, "0"), (None, "0"), (12345, "12,345")])
def test_format_count_groups_thousands(value, expected):
    """Counts are integers with thousands separators."""
    assert query_data.format_count(value) == expected


@pytest.mark.parametrize(
    "kind, value, expected",
    [
        ("percent", 12.5, "12.50%"),
        ("count", 7, "7"),
        ("float", 3.14159, "3.14"),
    ],
)
def test_format_answer_dispatches_on_kind(kind, value, expected):
    """``format_answer`` routes each spec kind to the right formatter."""
    assert query_data.format_answer(kind, value) == expected


def test_expected_keys_match_the_declared_specs():
    """The key list the template relies on is derived from the specs themselves."""
    assert tuple(query_data.EXPECTED_KEYS) == tuple(
        spec.key for spec in query_data.ANALYSIS_SPECS
    )
    assert len(set(query_data.EXPECTED_KEYS)) == len(query_data.EXPECTED_KEYS)


def test_every_spec_declares_a_known_kind():
    """Each question is formatted by one of the three supported formatters."""
    assert {spec.kind for spec in query_data.ANALYSIS_SPECS} <= {"count", "percent", "float"}


def test_analysis_items_pair_every_question_with_an_answer():
    """``get_analysis_items`` produces one question/answer pair per spec."""
    analysis = {key: None for key in query_data.EXPECTED_KEYS}
    items = query_data.get_analysis_items(analysis)

    assert len(items) == len(query_data.ANALYSIS_SPECS)
    for item in items:
        assert item["question"].endswith("?")
        assert item["answer"]


def test_missing_values_still_render_an_answer():
    """A key absent from the analysis dict renders a formatted fallback, not a crash."""
    items = query_data.get_analysis_items({})
    answers = {item["key"]: item["answer"] for item in items}

    assert answers["total_applicants"] == "0"
    assert answers["percent_international"] == "0.00%"
    assert answers["avg_gpa"] == "N/A"


def test_every_rendered_item_carries_an_answer_label(stub_client):
    """Each analysis item on the page is labelled ``Answer:``."""
    page = BeautifulSoup(stub_client.get("/analysis").get_data(as_text=True), "html.parser")
    items = page.find_all(attrs={"data-testid": "analysis-item"})

    assert items
    for item in items:
        answer = item.find(attrs={"data-testid": "analysis-answer"})
        assert answer.get_text(strip=True).startswith("Answer:")


def test_every_percentage_on_the_page_has_two_decimals(stub_client):
    """No percentage is rendered with varying precision."""
    text = stub_client.get("/analysis").get_data(as_text=True)
    matches = PERCENT_PATTERN.findall(text)

    assert matches, "expected at least one percentage on the analysis page"
    for decimals in matches:
        assert len(decimals) == 2


def test_a_long_decimal_percentage_is_rounded_on_the_page(stub_client):
    """The stub analysis reports 39.284; the page must show 39.28%."""
    text = stub_client.get("/analysis").get_data(as_text=True)

    assert "39.28%" in text
    assert "39.284" not in text


@pytest.mark.db
def test_run_queries_prints_labelled_answers(conn, capsys):
    """The CLI report prints the same questions and ``Answer:`` labels as the page."""
    query_data.run_queries()
    out = capsys.readouterr().out

    assert out.count("Answer:") == len(query_data.ANALYSIS_SPECS)
    for spec in query_data.ANALYSIS_SPECS:
        assert spec.question in out
