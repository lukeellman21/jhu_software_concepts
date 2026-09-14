"""
scrape.py - Scrapes applicant entries from Grad Cafe.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode, urlparse, urlunparse

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


class GradCafeScraper:
    BASE_URL = "https://www.thegradcafe.com/survey/index.php"

    def __init__(self, output_filepath: str = "applicant_data.json"):
        self.output_filepath = Path(output_filepath)
        self.data: List[Dict[str, Any]] = self.load_data()

    def _build_url(self, page: int) -> str:
        """Constructs Grad Cafe pagination URL using urllib."""
        parsed = urlparse(self.BASE_URL)
        query = {"pp": "250", "p": str(page)}
        new_query = urlencode(query)
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", new_query, ""))

    def _init_driver(self) -> webdriver.Chrome:
        """Configures Chrome driver with eager loading to prevent timeouts."""
        options = Options()
        # 'eager' means proceed once DOM is interactive (don't wait on slow ads)
        options.page_load_strategy = "eager"
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        return webdriver.Chrome(options=options)

    def _parse_row(self, row_soup: BeautifulSoup) -> Optional[Dict[str, Any]]:
        """Parses an applicant row entry based on GradCafe's table structure."""
        try:
            cells = row_soup.find_all("td")
            if len(cells) < 4:
                return None

            # Cell 0: School
            school = cells[0].get_text(" ", strip=True)
            if not school or "School" in school:
                return None

            # Cell 1: Program, Degree, Badges, Comments
            col_prog = cells[1]
            col_prog_text = col_prog.get_text(" ", strip=True)

            # Degree extraction
            degree = None
            if "Masters" in col_prog_text or "MS" in col_prog_text or "MA" in col_prog_text:
                degree = "Masters"
            elif "PhD" in col_prog_text:
                degree = "PhD"
            elif "MFA" in col_prog_text:
                degree = "MFA"

            # Term extraction (e.g. Spring 2027, Fall 2026)
            term_match = re.search(r"\b(Fall|Spring|Summer|Winter)\s+\d{4}\b", col_prog_text)
            term = term_match.group(0) if term_match else None

            # US / International
            us_intl = None
            if "International" in col_prog_text:
                us_intl = "International"
            elif "American" in col_prog_text:
                us_intl = "American"

            # GPA & GRE metrics
            gpa_match = re.search(r"GPA\s*([\d.]+)", col_prog_text, re.IGNORECASE)
            gre_tot = re.search(r"\bGRE\s*(\d{3})\b", col_prog_text, re.IGNORECASE)
            gre_v = re.search(r"GRE\s*V\s*(\d+)", col_prog_text, re.IGNORECASE)
            gre_aw = re.search(r"GRE\s*AW\s*([\d.]+)", col_prog_text, re.IGNORECASE)

            # Cell 2: Date Added
            date_added = cells[2].get_text(" ", strip=True)

            # Cell 3: Decision / Status
            status_text = cells[3].get_text(" ", strip=True)

            # Entry link
            link_tag = row_soup.find("a", href=lambda h: h and ("/result/" in h or "/survey/" in h))
            url_link = ""
            if link_tag and link_tag.has_attr("href"):
                url_link = link_tag["href"]
                if not url_link.startswith("http"):
                    url_link = "https://www.thegradcafe.com" + url_link

            # Raw program field combines School + Program
            raw_program = f"{school} - {col_prog_text}"

            return {
                "program": raw_program,
                "comments": col_prog_text,
                "date_added": date_added,
                "url": url_link,
                "status": status_text,
                "term": term,
                "US/International": us_intl,
                "GPA": f"GPA {gpa_match.group(1)}" if gpa_match else None,
                "GRE": gre_tot.group(1) if gre_tot else None,
                "GRE V": gre_v.group(1) if gre_v else None,
                "GRE AW": gre_aw.group(1) if gre_aw else None,
                "Degree": degree,
            }
        except Exception:
            return None

    def scrape_data(self, target_records: int = 30000) -> List[Dict[str, Any]]:
        """Main scraping loop through pages."""
        driver = self._init_driver()
        page = (len(self.data) // 250) + 1

        try:
            print(f"Starting at page {page} with {len(self.data)} existing records...")
            first_url = self._build_url(page)
            driver.get(first_url)

            print("\n*** ACTION REQUIRED ***")
            print("Check Chrome window: solve Cloudflare if visible.")
            input("Once the results table is loaded, press Enter here in the terminal to begin...\n")

            while len(self.data) < target_records:
                target_url = self._build_url(page)
                driver.get(target_url)

                try:
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.TAG_NAME, "tbody"))
                    )
                except Exception:
                    time.sleep(1)

                soup = BeautifulSoup(driver.page_source, "html.parser")
                tbody = soup.find("tbody")
                rows = tbody.find_all("tr") if tbody else soup.find_all("tr")

                found_in_page = 0
                for row in rows:
                    entry = self._parse_row(row)
                    if entry:
                        self.data.append(entry)
                        found_in_page += 1

                print(f"Page {page} collected {found_in_page} rows. Total records: {len(self.data)}")

                if found_in_page == 0:
                    print("No rows found. Stopping.")
                    break

                page += 1
                self.save_data()
                time.sleep(1.0)

        finally:
            driver.quit()
            self.save_data()

        return self.data

    def save_data(self) -> None:
        """Saves current data to JSON."""
        with open(self.output_filepath, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    def load_data(self) -> List[Dict[str, Any]]:
        """Loads saved data if continuing an earlier run."""
        if self.output_filepath.exists():
            with open(self.output_filepath, "r", encoding="utf-8") as f:
                try:
                    return json.load(f)
                except Exception:
                    return []
        return []


def scrape_data():
    scraper = GradCafeScraper()
    scraper.scrape_data(target_records=30000)


def save_data(data, filepath="applicant_data.json"):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_data(filepath="applicant_data.json"):
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    scrape_data()
