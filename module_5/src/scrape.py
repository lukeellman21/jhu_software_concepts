"""ETL extract layer: pull applicant entries from The Grad Café.

The scraper separates *fetching* a page from *parsing* it.  Fetching goes
through an injectable ``page_source_provider`` callable, which defaults to a
Selenium-driven Chrome session; the test suite passes a provider that returns
canned HTML, so no test ever touches the network.
"""
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence
from urllib.parse import urlencode, urlparse, urlunparse

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from . import fields

#: Signature of a page-source provider: ``provider(url) -> html``.
PageSourceProvider = Callable[[str], str]

#: Keys produced by :meth:`GradCafeScraper._parse_row`, i.e. the raw record shape.
RAW_KEYS: Sequence[str] = fields.RAW_KEYS


class GradCafeScraper:
    """Fetch and parse Grad Café survey pages.

    :param output_filepath: optional JSON file used to persist and resume a run.
    :param page_source_provider: callable returning the HTML for a URL.  When
        ``None``, a Selenium Chrome session is created lazily.
    :param pause_seconds: delay between page fetches when scraping live.
    :param wait_seconds: how long to wait for the results table to appear.
    :param records_per_page: value of the Grad Café ``pp`` query parameter.
    """

    BASE_URL = "https://www.thegradcafe.com/survey/index.php"

    def __init__(
        self,
        output_filepath: Optional[str] = None,
        page_source_provider: Optional[PageSourceProvider] = None,
        pause_seconds: float = 0.0,
        wait_seconds: float = 10.0,
        records_per_page: int = 250,
    ) -> None:
        self.output_filepath = Path(output_filepath) if output_filepath else None
        self.page_source_provider = page_source_provider
        self.pause_seconds = pause_seconds
        self.wait_seconds = wait_seconds
        self.records_per_page = records_per_page
        self._driver: Any = None
        self.data: List[Dict[str, Any]] = self.load_existing()

    # ------------------------------------------------------------------ fetch

    def _build_url(self, page: int) -> str:
        """Build the paginated survey URL for ``page``."""
        parsed = urlparse(self.BASE_URL)
        query = urlencode({"pp": str(self.records_per_page), "p": str(page)})
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", query, ""))

    def _init_driver(self) -> Any:
        """Create a Chrome driver configured for eager page loading."""
        options = Options()
        options.page_load_strategy = "eager"
        options.add_argument("--headless=new")
        options.add_argument("--disable-blink-features=AutomationControlled")
        # Selenium exposes Chrome through a lazy module __getattr__, which
        # Pylint cannot resolve statically; the class is callable at runtime.
        return webdriver.Chrome(options=options)  # pylint: disable=not-callable

    def _get_driver(self) -> Any:
        """Return the Chrome driver, creating it on first use."""
        if self._driver is None:
            self._driver = self._init_driver()
        return self._driver

    def _wait_for_table(self, driver: Any) -> bool:
        """Wait for a ``<tbody>`` to appear; return ``False`` on timeout."""
        try:
            WebDriverWait(driver, self.wait_seconds).until(
                EC.presence_of_element_located((By.TAG_NAME, "tbody"))
            )
            return True
        except TimeoutException:
            return False

    def _selenium_page_source(self, url: str) -> str:
        """Default page-source provider: load ``url`` in Chrome and return its HTML."""
        driver = self._get_driver()
        driver.get(url)
        self._wait_for_table(driver)
        return driver.page_source

    def fetch_page_source(self, page: int) -> str:
        """Return the HTML of survey ``page`` using the configured provider."""
        provider = self.page_source_provider or self._selenium_page_source
        return provider(self._build_url(page))

    def close(self) -> None:
        """Quit the Chrome driver if one was created."""
        if self._driver is not None:
            self._driver.quit()
            self._driver = None

    # ------------------------------------------------------------------ parse

    def _parse_row(self, row_soup: Any) -> Optional[Dict[str, Any]]:
        """Parse one ``<tr>`` into a raw record, or ``None`` if it is not a data row."""
        try:
            cells = row_soup.find_all("td")
            if len(cells) < 4:
                return None

            school = cells[0].get_text(" ", strip=True)
            if not school or "School" in school:
                return None

            details = cells[1].get_text(" ", strip=True)

            degree = None
            if any(token in details for token in ("Masters", "MS", "MA")):
                degree = "Masters"
            elif "PhD" in details:
                degree = "PhD"
            elif "MFA" in details:
                degree = "MFA"

            term_match = re.search(r"\b(Fall|Spring|Summer|Winter)\s+\d{4}\b", details)
            us_intl = None
            if "International" in details:
                us_intl = "International"
            elif "American" in details:
                us_intl = "American"

            gpa_match = re.search(r"GPA\s*([\d.]+)", details, re.IGNORECASE)
            gre_match = re.search(r"\bGRE\s*(\d{3})\b", details, re.IGNORECASE)
            gre_v_match = re.search(r"GRE\s*V\s*(\d+)", details, re.IGNORECASE)
            gre_aw_match = re.search(r"GRE\s*AW\s*([\d.]+)", details, re.IGNORECASE)

            link = row_soup.find("a", href=lambda h: h and ("/result/" in h or "/survey/" in h))
            entry_url = ""
            if link is not None:
                entry_url = link["href"]
                if not entry_url.startswith("http"):
                    entry_url = "https://www.thegradcafe.com" + entry_url

            return {
                "program": f"{school} - {details}",
                "comments": details,
                "date_added": cells[2].get_text(" ", strip=True),
                "url": entry_url,
                "status": cells[3].get_text(" ", strip=True),
                "term": term_match.group(0) if term_match else None,
                "US/International": us_intl,
                "GPA": f"GPA {gpa_match.group(1)}" if gpa_match else None,
                "GRE": gre_match.group(1) if gre_match else None,
                "GRE V": gre_v_match.group(1) if gre_v_match else None,
                "GRE AW": gre_aw_match.group(1) if gre_aw_match else None,
                "Degree": degree,
            }
        except (AttributeError, IndexError, KeyError, TypeError):
            # Malformed markup: skip the row rather than abort the whole page.
            return None

    def parse_page(self, html: str) -> List[Dict[str, Any]]:
        """Parse every data row of a survey page's HTML into raw records."""
        soup = BeautifulSoup(html, "html.parser")
        body = soup.find("tbody")
        rows = body.find_all("tr") if body else soup.find_all("tr")
        return [record for record in (self._parse_row(row) for row in rows) if record]

    # ------------------------------------------------------------------- run

    def scrape_data(
        self,
        target_records: int = 500,
        max_pages: int = 5,
        start_page: int = 1,
    ) -> List[Dict[str, Any]]:
        """Fetch pages until ``target_records`` or ``max_pages`` is reached.

        :param target_records: stop once this many records are held in total.
        :param max_pages: hard cap on the number of pages fetched.
        :param start_page: first page to fetch.
        :returns: every record collected so far, including any resumed from disk.
        """
        try:
            for offset in range(max_pages):
                if len(self.data) >= target_records:
                    break
                page = start_page + offset
                found = self.parse_page(self.fetch_page_source(page))
                self.data.extend(found)
                if not found:
                    break
                self.save_data()
                if self.pause_seconds:
                    time.sleep(self.pause_seconds)
        finally:
            self.close()
            self.save_data()
        return self.data

    # ------------------------------------------------------------ persistence

    def save_data(self) -> None:
        """Write the collected records to :attr:`output_filepath`, if one is set."""
        if self.output_filepath is None:
            return
        with open(self.output_filepath, "w", encoding="utf-8") as handle:
            json.dump(self.data, handle, indent=2, ensure_ascii=False)

    def load_existing(self) -> List[Dict[str, Any]]:
        """Load previously saved records so an interrupted run can resume."""
        if self.output_filepath is None or not self.output_filepath.exists():
            return []
        with open(self.output_filepath, "r", encoding="utf-8") as handle:
            try:
                return json.load(handle)
            except json.JSONDecodeError:
                return []


def pull_new_records(
    target_records: int = 250,
    max_pages: int = 1,
    page_source_provider: Optional[PageSourceProvider] = None,
    output_filepath: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Scrape a batch of records; the default ``scraper`` used by the web layer.

    :param target_records: how many records to aim for.
    :param max_pages: hard cap on pages fetched.
    :param page_source_provider: injected fetcher; ``None`` uses Selenium.
    :param output_filepath: optional JSON file to persist the batch to.
    :returns: the raw records.
    """
    scraper = GradCafeScraper(
        output_filepath=output_filepath,
        page_source_provider=page_source_provider,
    )
    return scraper.scrape_data(target_records=target_records, max_pages=max_pages)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Command-line entry point: ``python -m src.scrape --pages 2``."""
    parser = argparse.ArgumentParser(description="Scrape Grad Café survey pages.")
    parser.add_argument("--pages", type=int, default=1, help="maximum pages to fetch")
    parser.add_argument("--target", type=int, default=250, help="target record count")
    parser.add_argument("--out", default="applicant_data.json", help="output JSON file")
    args = parser.parse_args(argv)

    records = pull_new_records(
        target_records=args.target,
        max_pages=args.pages,
        output_filepath=args.out,
    )
    print(f"Scraped {len(records)} record(s) into {args.out}.")
    return len(records)


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    main()
