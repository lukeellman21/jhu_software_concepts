# Module 4: Pytest, Coverage, CI and Sphinx

A test-driven, documented version of the Grad Café analytics service: a Flask
analysis page backed by a PostgreSQL database, an ETL pipeline that fills it,
211 marked tests at 100% coverage, and Sphinx documentation.

- **Documentation:** https://lukeellman-jhu-software-concepts.readthedocs.io/en/latest/
- **CI:** [`.github/workflows/tests.yml`](../.github/workflows/tests.yml): starts PostgreSQL 16 and runs the full suite with coverage (see [`actions_success.png`](actions_success.png))
- **Coverage proof:** [`coverage_summary.txt`](coverage_summary.txt)

## Layout

```
module_4/
├── src/                 # application code
│   ├── flask_app.py     # create_app factory + routes
│   ├── scrape.py        # ETL extract  (injectable page-source provider)
│   ├── clean.py         # ETL transform
│   ├── load_data.py     # ETL load: schema, normalisation, idempotent insert
│   ├── query_data.py    # analysis SQL + formatters
│   ├── models.py        # SQLAlchemy ORM mapping
│   ├── orm_queries.py   # the Module-3 ORM report
│   ├── db.py            # DATABASE_URL resolution
│   ├── templates/       # analysis.html
│   └── static/          # style.css
├── tests/               # all test code
├── docs/                # Sphinx project (source + conf.py + built HTML)
├── data/                # 20-record sample dataset, so nothing needs the network
├── conftest.py          # puts module_4 on sys.path for `import src`
├── pytest.ini
├── requirements.txt
├── coverage_summary.txt
├── actions_success.png  # green CI run
└── README.md
```

## Setup

Requires Python 3.10+ and PostgreSQL 14+.

```bash
git clone git@github.com:lukeellman21/jhu_software_concepts.git
cd jhu_software_concepts
python3 -m venv module_4/.venv
source module_4/.venv/bin/activate
pip install -r module_4/requirements.txt
```

### PostgreSQL

```bash
createdb gradcafe        # application database
createdb gradcafe_test   # throwaway database for the test suite
export DATABASE_URL=postgresql://localhost/gradcafe
```

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | `postgresql://localhost/gradcafe` | connection string for the app, loader and queries |
| `TEST_DATABASE_URL` | `postgresql://localhost/gradcafe_test` | database the test suite uses; your `DATABASE_URL` is never touched |
| `GRADCAFE_DATA_FILE` | `module_4/data/sample_applicant_data.json` | dataset read by the loader |
| `FLASK_SECRET_KEY` | random per process | Flask session key; nothing is hard-coded |

No credentials are stored in the repository.

### Load data and run the app

```bash
cd module_4
python -m src.load_data --reset          # load the bundled sample dataset
flask --app src.flask_app:create_app run --debug
```

Open <http://127.0.0.1:5000/analysis> (`/` redirects there).

| Route | Method | Behaviour |
| --- | --- | --- |
| `/` | GET | redirect to `/analysis` |
| `/analysis` | GET | the analysis page: both buttons, one `Answer:` per question. Always `200`: if PostgreSQL is unreachable the page still renders, with a `data-testid="db-error"` banner instead of a 500 |
| `/pull-data` | POST | `200 {"ok": true, "rows_loaded": n}`; `409 {"busy": true}` while a pull runs; `500` if the loader fails |
| `/update-analysis` | POST | `200 {"ok": true}`; `409 {"busy": true}` while a pull runs; `503` if PostgreSQL is unreachable |
| `/status` | GET | JSON snapshot of the pipeline state |

## Run the tests

Run from the **repository root** so `--cov=module_4/src` resolves:

```bash
pytest module_4
pytest module_4 -m "web or buttons or analysis or db or integration"   # whole suite
pytest module_4 -m buttons                                             # one slice
```

`pytest.ini` also lists `--cov=src`, so `cd module_4 && pytest` works too. Every
run enforces 100% coverage of `module_4/src`; the committed summary is in
`coverage_summary.txt`.

Every test carries one of the markers `web`, `buttons`, `analysis`, `db` or
`integration`, and there are no unmarked tests. No test reaches the network, opens
a browser, or sleeps waiting on the busy flag.

| File | Marker | Covers |
| --- | --- | --- |
| `tests/test_flask_page.py` | `web` | factory, routes, rendering, selectors |
| `tests/test_buttons.py` | `buttons` | both POST endpoints, busy gating, error path |
| `tests/test_analysis_format.py` | `analysis` | `Answer:` labels, two-decimal percentages |
| `tests/test_db_insert.py` | `db` | schema, inserts, idempotency, query function |
| `tests/test_db_layer.py` | `db` | `DATABASE_URL` handling, ORM mapping and report |
| `tests/test_etl.py` | `integration` | scraper, cleaner, row normalisation |
| `tests/test_integration_end_to_end.py` | `integration` | pull → update → render, repeated pulls |

UI assertions use stable selectors: `data-testid="pull-data-btn"` and
`data-testid="update-analysis-btn"`, plus `analysis-item` / `analysis-answer`
for the rendered answers.

## Documentation

Published at <https://lukeellman-jhu-software-concepts.readthedocs.io/en/latest/>. Build it locally:

```bash
cd module_4
sphinx-build -b html docs docs/_build/html
open docs/_build/html/index.html
```

The docs cover setup and environment variables, the web/ETL/DB architecture, an
autodoc API reference for every module, a testing guide (markers, selectors,
fixtures, doubles), operational notes (busy-state policy, idempotency and
uniqueness keys) and troubleshooting.

## Notes on the Module-3 carry-over

- The Module-3 code moved into `src/`, with the Flask app rebuilt around a
  `create_app(...)` factory and JSON endpoints so it can be driven by the test
  client.
- The column set is unchanged. The only schema change is that the fields the
  loader always populates are now declared `NOT NULL`, which turns the loader's
  guarantee into a database-enforced one.
- `p_id` is now derived from the Grad Café result URL, which is what makes
  repeated pulls idempotent.
- The 12 MB scraped datasets stay in `module_3/`; `module_4/data/` carries a
  20-record sample of the distinct entries, so the loader and the tests
  never need the network. The Module-2 scrape recorded 30,000 rows but only 20
  distinct result URLs, so the sample is de-duplicated on `url`.
