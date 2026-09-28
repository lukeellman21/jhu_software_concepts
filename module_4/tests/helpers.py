"""Shared test doubles and fixtures data.

Nothing here talks to the network or to a real browser: :class:`Recorder`
replaces the scraper/loader/analysis callables, and :func:`survey_page_html`
builds the Grad Café markup that the parser tests consume.
"""
from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional, Sequence

#: Four raw records in the exact shape :meth:`src.scrape.GradCafeScraper._parse_row` emits.
RAW_RECORDS: Sequence[Dict[str, Any]] = (
    {
        "program": "Johns Hopkins University - Computer Science PhD",
        "comments": "Computer Science PhD Fall 2026 International GPA 3.90",
        "date_added": "Sep 12, 2026",
        "url": "https://www.thegradcafe.com/result/1000001",
        "status": "Accepted on Sep 11",
        "term": "Fall 2026",
        "US/International": "International",
        "GPA": "GPA 3.90",
        "GRE": "167",
        "GRE V": "160",
        "GRE AW": "4.5",
        "Degree": "PhD",
    },
    {
        "program": "Stanford University - Computer Science PhD",
        "comments": "Computer Science PhD Fall 2026 American GPA 3.95",
        "date_added": "Sep 10, 2026",
        "url": "https://www.thegradcafe.com/result/1000002",
        "status": "Accepted on Sep 09",
        "term": "Fall 2026",
        "US/International": "American",
        "GPA": "GPA 3.95",
        "GRE": "169",
        "GRE V": "163",
        "GRE AW": "5.0",
        "Degree": "PhD",
    },
    {
        "program": "Carnegie Mellon University - Computer Science Masters",
        "comments": "Computer Science Masters Fall 2025 American GPA 3.40",
        "date_added": "Aug 30, 2025",
        "url": "https://www.thegradcafe.com/result/1000003",
        "status": "Rejected on Aug 29",
        "term": "Fall 2025",
        "US/International": "American",
        "GPA": "GPA 3.40",
        "GRE": None,
        "GRE V": None,
        "GRE AW": None,
        "Degree": "Masters",
    },
    {
        "program": "Bennington College - Creative Writing Poetry MFA",
        "comments": "Creative Writing Poetry MFA",
        "date_added": "Sep 12, 2026",
        "url": "https://www.thegradcafe.com/result/1000004",
        "status": "Wait listed on Sep 01",
        "term": None,
        "US/International": None,
        "GPA": None,
        "GRE": None,
        "GRE V": None,
        "GRE AW": None,
        "Degree": "MFA",
    },
)


def raw_records(count: Optional[int] = None) -> List[Dict[str, Any]]:
    """Return a deep copy of :data:`RAW_RECORDS` so tests cannot affect each other."""
    records = copy.deepcopy(list(RAW_RECORDS))
    return records if count is None else records[:count]


class Recorder:
    """A callable test double that records its calls.

    :param result: value returned to the caller (or a callable to delegate to).
    :param error: exception instance raised instead of returning.
    """

    def __init__(self, result: Any = None, error: Optional[BaseException] = None) -> None:
        self.result = result
        self.error = error
        self.calls: List[tuple] = []

    @property
    def call_count(self) -> int:
        """How many times the double has been called."""
        return len(self.calls)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append((args, kwargs))
        if self.error is not None:
            raise self.error
        if callable(self.result):
            return self.result(*args, **kwargs)
        return self.result


def survey_page_html(rows: Sequence[str], with_tbody: bool = True) -> str:
    """Wrap pre-rendered ``<tr>`` strings in a Grad Café-shaped table."""
    body = "\n".join(rows)
    if with_tbody:
        return f"<html><body><table><tbody>{body}</tbody></table></body></html>"
    return f"<html><body><table>{body}</table></body></html>"


def survey_row(
    school: str = "Johns Hopkins University",
    details: str = "Computer Science PhD Fall 2026 International GPA 3.90 GRE 167 GRE V 160 GRE AW 4.5",
    date_added: str = "Sep 12, 2026",
    status: str = "Accepted on Sep 11",
    href: Optional[str] = "/result/1000001",
) -> str:
    """Render a single Grad Café results row."""
    link = f'<a href="{href}">See more</a>' if href else ""
    return (
        "<tr>"
        f"<td>{school}</td>"
        f"<td>{details}{link}</td>"
        f"<td>{date_added}</td>"
        f"<td>{status}</td>"
        "</tr>"
    )
