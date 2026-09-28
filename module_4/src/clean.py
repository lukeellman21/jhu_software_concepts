"""ETL transform layer: sanitise raw scraped records.

:func:`clean_data` is deliberately conservative -- it normalises whitespace
and coerces the numeric fields, but leaves the record keys exactly as the
scraper produced them so that :func:`src.load_data.normalize_record` remains the
single place where database columns are decided.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

#: Fields carried through :func:`clean_record`, in output order.
CLEAN_KEYS: Sequence[str] = (
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


def clean_text(text: Optional[str]) -> Optional[str]:
    """Collapse runs of whitespace and strip the result, or return ``None``."""
    if not text:
        return None
    cleaned = re.sub(r"\s+", " ", str(text)).strip()
    return cleaned or None


def clean_gpa(raw_gpa: Any) -> Optional[float]:
    """Extract a plausible GPA (0.0-5.0) from messy input."""
    if raw_gpa in (None, ""):
        return None
    match = re.search(r"(\d+(?:\.\d+)?)", str(raw_gpa))
    if not match:
        return None
    value = float(match.group(1))
    if 0.0 <= value <= 5.0:
        return round(value, 2)
    return None


def clean_gre(raw_gre: Any) -> Optional[int]:
    """Extract a GRE score, accepting both the 130-170 and 200-800 scales."""
    if raw_gre in (None, ""):
        return None
    match = re.search(r"\b(\d+)\b", str(raw_gre))
    if not match:
        return None
    value = int(match.group(1))
    if 130 <= value <= 340 or 200 <= value <= 800:
        return value
    return None


def clean_gre_aw(raw_aw: Any) -> Optional[float]:
    """Extract the GRE Analytical Writing score (0.0-6.0)."""
    if raw_aw in (None, ""):
        return None
    match = re.search(r"(\d+(?:\.\d+)?)", str(raw_aw))
    if not match:
        return None
    value = float(match.group(1))
    if 0.0 <= value <= 6.0:
        return round(value, 2)
    return None


def clean_record(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Clean a single raw record, returning a dict keyed by :data:`CLEAN_KEYS`."""
    return {
        "program": clean_text(entry.get("program")),
        "comments": clean_text(entry.get("comments")),
        "date_added": clean_text(entry.get("date_added")),
        "url": clean_text(entry.get("url")),
        "status": clean_text(entry.get("status")),
        "term": clean_text(entry.get("term")),
        "US/International": clean_text(entry.get("US/International")),
        "GPA": clean_gpa(entry.get("GPA")),
        "GRE": clean_gre(entry.get("GRE")),
        "GRE V": clean_gre(entry.get("GRE V")),
        "GRE AW": clean_gre_aw(entry.get("GRE AW")),
        "Degree": clean_text(entry.get("Degree")),
    }


def clean_data(records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Clean a batch of raw records with :func:`clean_record`.

    This is the module's public entry point; :func:`clean_records` is kept as an
    alias so existing callers keep working.

    :param records: raw records as produced by :mod:`src.scrape`.
    :returns: one cleaned record per input record, keyed by :data:`CLEAN_KEYS`.
    """
    return [clean_record(entry) for entry in records]


#: Alias for :func:`clean_data`.
clean_records = clean_data


def clean_file(input_path: str, output_path: str) -> int:
    """Clean a JSON dataset on disk and write the result.

    :param input_path: JSON array of raw records.
    :param output_path: destination for the cleaned array.
    :returns: number of records written.
    :raises FileNotFoundError: when ``input_path`` does not exist.
    """
    source = Path(input_path)
    if not source.exists():
        raise FileNotFoundError(f"{input_path} not found")

    with open(source, "r", encoding="utf-8") as handle:
        raw = json.load(handle)

    cleaned = clean_data(raw)
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(cleaned, handle, indent=2, ensure_ascii=False)
    return len(cleaned)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Command-line entry point: ``python -m src.clean --in raw.json``."""
    parser = argparse.ArgumentParser(description="Clean scraped Grad Café records.")
    parser.add_argument("--in", dest="input_path", default="applicant_data.json")
    parser.add_argument("--out", dest="output_path", default="cleaned_data.json")
    args = parser.parse_args(argv)

    count = clean_file(args.input_path, args.output_path)
    print(f"Cleaned {count} record(s) into {args.output_path}.")
    return count


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    main()
