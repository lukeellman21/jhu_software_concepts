"""
clean.py - Pre-cleans raw applicant records scraped from Grad Cafe.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


def clean_text(text: Optional[str]) -> Optional[str]:
    """Strips extra whitespace and collapses internal spaces."""
    if not text:
        return None
    cleaned = re.sub(r"\s+", " ", text).strip()
    return cleaned if cleaned else None


def clean_gpa(raw_gpa: Optional[str]) -> Optional[float]:
    """Extracts floating-point GPA value if valid."""
    if not raw_gpa:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)", raw_gpa)
    if match:
        try:
            val = float(match.group(1))
            if 0.0 <= val <= 5.0:
                return round(val, 2)
        except ValueError:
            pass
    return None


def clean_gre(raw_gre: Optional[str]) -> Optional[int]:
    """Extracts integer GRE score if within valid ranges."""
    if not raw_gre:
        return None
    match = re.search(r"\b(\d+)\b", str(raw_gre))
    if match:
        try:
            val = int(match.group(1))
            if 130 <= val <= 340 or 200 <= val <= 800:
                return val
        except ValueError:
            pass
    return None


def clean_records(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Iterates through and sanitizes record fields."""
    cleaned_records = []

    for entry in records:
        cleaned_entry = {
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
            "GRE AW": entry.get("GRE AW"),
            "Degree": clean_text(entry.get("Degree")),
        }
        cleaned_records.append(cleaned_entry)

    return cleaned_records


def main(input_path: str = "applicant_data.json", output_path: str = "cleaned_data.json"):
    in_p = Path(input_path)
    out_p = Path(output_path)

    if not in_p.exists():
        print(f"Error: {input_path} not found.")
        return

    print(f"Loading {input_path}...")
    with open(in_p, "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"Loaded {len(data)} raw records. Cleaning...")
    cleaned = clean_records(data)

    print(f"Saving to {output_path}...")
    with open(out_p, "w", encoding="utf-8") as f:
        json.dump(cleaned, f, indent=2, ensure_ascii=False)

    print(f"Done! Cleaned {len(cleaned)} records successfully.")


if __name__ == "__main__":
    main()
