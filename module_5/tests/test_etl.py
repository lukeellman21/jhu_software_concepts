"""ETL unit coverage: extract (scrape), transform (clean) and row normalisation.

Marker: ``integration`` -- these exercise the extract/transform half of the
end-to-end flow.  Nothing here opens a browser or reaches the network: page
HTML is injected through the scraper's ``page_source_provider`` seam and the
Selenium fallback is exercised against test doubles.
"""
from __future__ import annotations

import json
from datetime import date

import pytest
from selenium.common.exceptions import TimeoutException

from helpers import Recorder, raw_records, survey_page_html, survey_row
from src import clean, load_data, scrape

pytestmark = pytest.mark.integration


class FakeDriver:
    """Stands in for a Selenium Chrome driver."""

    def __init__(self, page_source: str = "<html></html>") -> None:
        self.page_source = page_source
        self.visited: list[str] = []
        self.quit_calls = 0

    def get(self, url: str) -> None:
        self.visited.append(url)

    def quit(self) -> None:
        self.quit_calls += 1


class SucceedingWait:
    """``WebDriverWait`` double whose condition resolves immediately."""

    def __init__(self, driver, timeout):
        self.driver = driver

    def until(self, condition):
        return True


class TimingOutWait:
    """``WebDriverWait`` double that always times out."""

    def __init__(self, driver, timeout):
        self.driver = driver

    def until(self, condition):
        raise TimeoutException("no tbody")


def provider_for(*pages: str) -> Recorder:
    """Return a page-source provider double serving ``pages`` in order."""
    pages = list(pages)

    def serve(url: str) -> str:
        return pages.pop(0) if pages else survey_page_html([])

    return Recorder(result=serve)


class TestScraperUrls:
    """URL construction."""

    def test_build_url_paginates(self):
        scraper = scrape.GradCafeScraper()
        assert scraper._build_url(3) == (
            "https://www.thegradcafe.com/survey/index.php?pp=250&p=3"
        )

    def test_records_per_page_is_configurable(self):
        scraper = scrape.GradCafeScraper(records_per_page=20)
        assert "pp=20" in scraper._build_url(1)


class TestSeleniumFallback:
    """The default page-source provider, exercised against doubles."""

    def test_init_driver_configures_chrome(self, monkeypatch):
        captured = {}

        def fake_chrome(options):
            captured["options"] = options
            return FakeDriver()

        monkeypatch.setattr(scrape.webdriver, "Chrome", fake_chrome)
        driver = scrape.GradCafeScraper()._init_driver()

        assert isinstance(driver, FakeDriver)
        assert captured["options"].page_load_strategy == "eager"
        assert "--headless=new" in captured["options"].arguments

    def test_driver_is_created_once_and_reused(self, monkeypatch):
        created = []

        def fake_chrome(options):
            created.append(options)
            return FakeDriver()

        monkeypatch.setattr(scrape.webdriver, "Chrome", fake_chrome)
        scraper = scrape.GradCafeScraper()

        assert scraper._get_driver() is scraper._get_driver()
        assert len(created) == 1

    def test_wait_for_table_reports_success(self, monkeypatch):
        monkeypatch.setattr(scrape, "WebDriverWait", SucceedingWait)
        assert scrape.GradCafeScraper()._wait_for_table(FakeDriver()) is True

    def test_wait_for_table_survives_a_timeout(self, monkeypatch):
        monkeypatch.setattr(scrape, "WebDriverWait", TimingOutWait)
        assert scrape.GradCafeScraper()._wait_for_table(FakeDriver()) is False

    def test_page_source_comes_from_the_driver(self, monkeypatch):
        html = survey_page_html([survey_row()])
        driver = FakeDriver(page_source=html)
        monkeypatch.setattr(scrape.webdriver, "Chrome", lambda options: driver)
        monkeypatch.setattr(scrape, "WebDriverWait", SucceedingWait)

        scraper = scrape.GradCafeScraper()
        source = scraper.fetch_page_source(2)

        assert source == html
        assert driver.visited == [scraper._build_url(2)]

    def test_close_quits_the_driver_once(self, monkeypatch):
        driver = FakeDriver()
        monkeypatch.setattr(scrape.webdriver, "Chrome", lambda options: driver)
        scraper = scrape.GradCafeScraper()
        scraper._get_driver()

        scraper.close()
        scraper.close()

        assert driver.quit_calls == 1

    def test_close_is_a_no_op_without_a_driver(self):
        scrape.GradCafeScraper().close()


class TestRowParsing:
    """Turning survey markup into raw records."""

    def test_a_complete_row_is_parsed(self):
        html = survey_page_html([survey_row()])
        record = scrape.GradCafeScraper().parse_page(html)[0]

        assert set(record) == set(scrape.RAW_KEYS)
        assert record["program"].startswith("Johns Hopkins University - ")
        assert record["date_added"] == "Sep 12, 2026"
        assert record["status"] == "Accepted on Sep 11"
        assert record["term"] == "Fall 2026"
        assert record["US/International"] == "International"
        assert record["GPA"] == "GPA 3.90"
        assert record["GRE"] == "167"
        assert record["GRE V"] == "160"
        assert record["GRE AW"] == "4.5"
        assert record["Degree"] == "PhD"
        assert record["url"] == "https://www.thegradcafe.com/result/1000001"

    def test_header_and_short_rows_are_skipped(self):
        html = survey_page_html(
            [
                "<tr><th>School</th><th>Program</th><th>Added</th><th>Decision</th></tr>",
                "<tr><td>School</td><td>x</td><td>y</td><td>z</td></tr>",
                "<tr><td></td><td>x</td><td>y</td><td>z</td></tr>",
                "<tr><td>Only</td><td>two</td></tr>",
                survey_row(),
            ]
        )
        assert len(scrape.GradCafeScraper().parse_page(html)) == 1

    @pytest.mark.parametrize(
        "details, expected_degree",
        [
            ("Computer Science Masters Fall 2026", "Masters"),
            ("Computer Science PhD Fall 2026", "PhD"),
            ("Creative Writing Poetry MFA", "MFA"),
            ("Computer Science Fall 2026", None),
        ],
    )
    def test_degree_is_detected(self, details, expected_degree):
        html = survey_page_html([survey_row(details=details)])
        assert scrape.GradCafeScraper().parse_page(html)[0]["Degree"] == expected_degree

    @pytest.mark.parametrize(
        "details, expected",
        [
            ("Computer Science PhD American", "American"),
            ("Computer Science PhD International", "International"),
            ("Computer Science PhD", None),
        ],
    )
    def test_origin_is_detected(self, details, expected):
        html = survey_page_html([survey_row(details=details)])
        assert scrape.GradCafeScraper().parse_page(html)[0]["US/International"] == expected

    def test_missing_metrics_stay_none(self):
        html = survey_page_html([survey_row(details="Computer Science PhD")])
        record = scrape.GradCafeScraper().parse_page(html)[0]

        assert record["term"] is None
        assert record["GPA"] is None
        assert record["GRE"] is None
        assert record["GRE V"] is None
        assert record["GRE AW"] is None

    @pytest.mark.parametrize(
        "href, expected",
        [
            (None, ""),
            ("/result/55", "https://www.thegradcafe.com/result/55"),
            ("https://www.thegradcafe.com/result/55", "https://www.thegradcafe.com/result/55"),
        ],
    )
    def test_entry_links_are_absolute(self, href, expected):
        html = survey_page_html([survey_row(href=href)])
        assert scrape.GradCafeScraper().parse_page(html)[0]["url"] == expected

    def test_malformed_markup_is_skipped_rather_than_fatal(self):
        assert scrape.GradCafeScraper()._parse_row(None) is None

    def test_rows_outside_a_tbody_are_still_found(self):
        html = survey_page_html([survey_row()], with_tbody=False)
        assert len(scrape.GradCafeScraper().parse_page(html)) == 1


class TestScrapeLoop:
    """The paging loop and its stop conditions."""

    def test_stops_once_the_target_is_reached(self):
        page = survey_page_html([survey_row(), survey_row(href="/result/2")])
        provider = provider_for(page, page)
        scraper = scrape.GradCafeScraper(page_source_provider=provider)

        data = scraper.scrape_data(target_records=2, max_pages=5)

        assert len(data) == 2
        assert provider.call_count == 1

    def test_stops_on_an_empty_page(self):
        provider = provider_for(survey_page_html([]))
        scraper = scrape.GradCafeScraper(page_source_provider=provider)

        assert scraper.scrape_data(target_records=100, max_pages=5) == []
        assert provider.call_count == 1

    def test_pages_are_fetched_in_order(self):
        rows = [survey_page_html([survey_row(href=f"/result/{i}")]) for i in range(3)]
        provider = provider_for(*rows)
        scraper = scrape.GradCafeScraper(page_source_provider=provider)

        scraper.scrape_data(target_records=3, max_pages=3, start_page=4)

        assert [call[0][0] for call in provider.calls] == [
            scraper._build_url(page) for page in (4, 5, 6)
        ]

    def test_pause_between_pages_is_honoured(self, monkeypatch):
        sleeper = Recorder()
        monkeypatch.setattr(scrape.time, "sleep", sleeper)
        page = survey_page_html([survey_row()])
        scraper = scrape.GradCafeScraper(
            page_source_provider=provider_for(page, page), pause_seconds=0.25
        )

        scraper.scrape_data(target_records=2, max_pages=2)

        assert sleeper.calls == [((0.25,), {})] * 2

    def test_progress_is_saved_and_resumed(self, tmp_path):
        target = tmp_path / "applicant_data.json"
        page = survey_page_html([survey_row()])

        first = scrape.GradCafeScraper(
            output_filepath=str(target), page_source_provider=provider_for(page)
        )
        first.scrape_data(target_records=1, max_pages=1)

        assert json.loads(target.read_text(encoding="utf-8"))

        resumed = scrape.GradCafeScraper(output_filepath=str(target))
        assert len(resumed.data) == 1

    def test_nothing_is_written_without_an_output_path(self, tmp_path):
        scraper = scrape.GradCafeScraper(
            page_source_provider=provider_for(survey_page_html([survey_row()]))
        )
        scraper.scrape_data(target_records=1, max_pages=1)

        assert list(tmp_path.iterdir()) == []

    def test_a_corrupt_resume_file_is_ignored(self, tmp_path):
        target = tmp_path / "applicant_data.json"
        target.write_text("{not json", encoding="utf-8")

        assert scrape.GradCafeScraper(output_filepath=str(target)).data == []

    def test_a_missing_resume_file_is_ignored(self, tmp_path):
        target = tmp_path / "absent.json"
        assert scrape.GradCafeScraper(output_filepath=str(target)).data == []


class TestScraperEntryPoints:
    """The helpers the web layer and the CLI call."""

    def test_pull_new_records_uses_the_injected_provider(self):
        provider = provider_for(survey_page_html([survey_row()]))
        records = scrape.pull_new_records(
            target_records=1, max_pages=1, page_source_provider=provider
        )

        assert len(records) == 1
        assert provider.call_count == 1

    def test_cli_reports_what_it_scraped(self, monkeypatch, capsys, tmp_path):
        monkeypatch.setattr(scrape, "pull_new_records", Recorder(result=raw_records(2)))
        out_path = tmp_path / "out.json"

        count = scrape.main(["--pages", "2", "--target", "10", "--out", str(out_path)])

        assert count == 2
        assert f"Scraped 2 record(s) into {out_path}." in capsys.readouterr().out


class TestClean:
    """The transform stage."""

    @pytest.mark.parametrize(
        "raw, expected",
        [("  spaced   out ", "spaced out"), ("", None), (None, None), ("   ", None)],
    )
    def test_clean_text(self, raw, expected):
        assert clean.clean_text(raw) == expected

    @pytest.mark.parametrize(
        "raw, expected",
        [("GPA 3.90", 3.9), ("3.876", 3.88), ("GPA 9.9", None), ("n/a", None), (None, None), ("", None)],
    )
    def test_clean_gpa(self, raw, expected):
        assert clean.clean_gpa(raw) == expected

    @pytest.mark.parametrize(
        "raw, expected",
        [("167", 167), ("GRE 720", 720), ("12", None), ("none", None), (None, None), ("", None)],
    )
    def test_clean_gre(self, raw, expected):
        assert clean.clean_gre(raw) == expected

    @pytest.mark.parametrize(
        "raw, expected",
        [("4.5", 4.5), (5, 5.0), ("9.0", None), ("n/a", None), (None, None), ("", None)],
    )
    def test_clean_gre_aw(self, raw, expected):
        assert clean.clean_gre_aw(raw) == expected

    def test_clean_record_keeps_the_raw_key_names(self):
        cleaned = clean.clean_record(raw_records(1)[0])

        assert set(cleaned) == set(clean.CLEAN_KEYS)
        assert cleaned["GPA"] == 3.9
        assert cleaned["GRE"] == 167
        assert cleaned["GRE AW"] == 4.5

    def test_clean_data_processes_the_batch(self):
        cleaned = clean.clean_data(raw_records())

        assert len(cleaned) == len(raw_records())
        assert set(cleaned[0]) == set(clean.CLEAN_KEYS)

    def test_clean_records_is_an_alias_for_clean_data(self):
        """The documented entry point is ``clean_data``; the old name still works."""
        assert clean.clean_records is clean.clean_data
        assert clean.clean_records(raw_records()) == clean.clean_data(raw_records())

    def test_clean_file_round_trip(self, tmp_path):
        source = tmp_path / "raw.json"
        target = tmp_path / "clean.json"
        source.write_text(json.dumps(raw_records()), encoding="utf-8")

        count = clean.clean_file(str(source), str(target))

        assert count == len(raw_records())
        assert len(json.loads(target.read_text(encoding="utf-8"))) == count

    def test_clean_file_rejects_a_missing_input(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            clean.clean_file(str(tmp_path / "absent.json"), str(tmp_path / "out.json"))

    def test_cli_reports_what_it_cleaned(self, tmp_path, capsys):
        source = tmp_path / "raw.json"
        target = tmp_path / "clean.json"
        source.write_text(json.dumps(raw_records(2)), encoding="utf-8")

        count = clean.main(["--in", str(source), "--out", str(target)])

        assert count == 2
        assert f"Cleaned 2 record(s) into {target}." in capsys.readouterr().out


class TestRowNormalisation:
    """Mapping raw records onto database rows."""

    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("Computer Science PhD", "PhD"),
            ("Ph.D in Physics", "PhD"),
            ("Masters in Data Science", "Masters"),
            ("Creative Writing MFA", "Masters"),
            ("Undeclared", "Other"),
            (None, "Other"),
        ],
    )
    def test_extract_degree(self, raw, expected):
        assert load_data.extract_degree(raw) == expected

    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("Johns Hopkins University - Computer Science", ("Johns Hopkins University", "Computer Science")),
            ("A - B - C", ("A", "B - C")),
            ("Solo Program", ("Solo Program", "Solo Program")),
            (None, ("Unknown", "Unknown")),
        ],
    )
    def test_extract_university_and_program(self, raw, expected):
        assert load_data.extract_university_and_program(raw) == expected

    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("Accepted on Sep 11", "Accepted"),
            ("Rejected", "Rejected"),
            ("Denied via email", "Rejected"),
            ("Interview scheduled", "Interview"),
            ("Wait listed", "Waitlisted"),
            ("Other", "Applied"),
            (None, "Applied"),
        ],
    )
    def test_normalize_status(self, raw, expected):
        assert load_data.normalize_status(raw) == expected

    @pytest.mark.parametrize(
        "raw, expected",
        [(None, None), (3.5, 3.5), (4, 4.0), ("GPA 3.90", 3.9), ("n/a", None), ("1.2.3", None)],
    )
    def test_parse_float(self, raw, expected):
        assert load_data.parse_float(raw) == expected

    @pytest.mark.parametrize(
        "raw, expected",
        [
            (None, None),
            ("", None),
            (date(2026, 9, 12), date(2026, 9, 12)),
            ("2026-09-12", date(2026, 9, 12)),
            ("09/12/2026", date(2026, 9, 12)),
            ("Sep 12, 2026", date(2026, 9, 12)),
            ("September 12, 2026", date(2026, 9, 12)),
            ("sometime last week", None),
        ],
    )
    def test_parse_date(self, raw, expected):
        assert load_data.parse_date(raw) == expected

    def test_p_id_prefers_an_explicit_id(self):
        assert load_data.derive_p_id({"p_id": "42"}) == 42
        assert load_data.derive_p_id({"id": 7}) == 7

    def test_p_id_falls_back_to_the_result_url(self):
        record = {"p_id": "not-a-number", "url": "https://www.thegradcafe.com/result/1020482"}
        assert load_data.derive_p_id(record) == 1020482

    def test_p_id_hashes_records_without_a_url(self):
        record = {"program": "A - B", "comments": "c", "date_added": "d", "status": "Accepted"}

        first = load_data.derive_p_id(record)
        again = load_data.derive_p_id(dict(record))

        assert first == again
        assert first != load_data.derive_p_id({**record, "comments": "different"})

    def test_p_id_uses_the_fallback_for_an_empty_record(self):
        assert load_data.derive_p_id({}, fallback=9) == 9

    def test_normalize_record_fills_every_required_field(self):
        row = load_data.normalize_record({}, index=3)

        assert set(row) == set(load_data.COLUMNS)
        for field in load_data.REQUIRED_FIELDS:
            assert row[field] is not None
        assert row["p_id"] == 3
        assert row["term"] == "Unknown"
        assert row["status"] == "Applied"
        assert row["degree"] == "Other"

    def test_normalize_record_maps_the_raw_scraper_keys(self):
        row = load_data.normalize_record(raw_records(1)[0])

        assert row["p_id"] == 1000001
        assert row["us_or_international"] == "International"
        assert row["gpa"] == 3.9
        assert row["gre"] == 167.0
        assert row["gre_v"] == 160.0
        assert row["gre_aw"] == 4.5
        assert row["date_added"] == date(2026, 9, 12)
        assert row["llm_generated_university"] == "Johns Hopkins University"

    def test_normalize_record_accepts_database_column_names(self):
        row = load_data.normalize_record(
            {
                "p_id": 5,
                "program": "X - Y",
                "us_or_international": "American",
                "gpa": 3.1,
                "llm_generated_program": "Y",
                "llm_generated_university": "X",
                "degree": "PhD",
            }
        )

        assert row["us_or_international"] == "American"
        assert row["gpa"] == 3.1
        assert row["llm_generated_program"] == "Y"

    def test_normalize_records_numbers_the_batch(self):
        rows = load_data.normalize_records([{}, {}])
        assert [row["p_id"] for row in rows] == [1, 2]
