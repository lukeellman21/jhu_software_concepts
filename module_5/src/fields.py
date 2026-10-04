"""The field names shared across the ETL stages.

Declared once here so that :mod:`src.scrape` (which produces them) and
:mod:`src.clean` (which consumes them) cannot drift apart, and so the same
tuple is not repeated in two modules.
"""
from __future__ import annotations

from typing import Sequence

#: Keys produced by the scraper and carried through the cleaner, in order.
RAW_KEYS: Sequence[str] = (
    "program",
    "comments",
    "date_added",
    "url",
    "status",
    "term",
    "US/International",
    "GPA",
    "GRE",
    "GRE V",
    "GRE AW",
    "Degree",
)
