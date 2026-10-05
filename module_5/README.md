# Module 5: Software Assurance and Security Hardening

The Grad Café analytics service, hardened: every SQL statement composed with
`psycopg.sql` and parameterised, every query capped by an enforced `LIMIT`,
credentials in the environment, a least-privilege database role, a 10.00/10
Pylint score, a generated dependency graph, and CI that enforces all of it.

- **Documentation:** https://lukeellman-jhu-software-concepts.readthedocs.io/en/latest/
- **CI:** [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) runs Pylint, the dependency graph, Snyk and Pytest
- **Evidence:** [`pylint_report.txt`](pylint_report.txt), [`dependency.svg`](dependency.svg), [`snyk-analysis.png`](snyk-analysis.png), [`snyk-code-analysis.png`](snyk-code-analysis.png), [`coverage_summary.txt`](coverage_summary.txt)
- **Report:** [`module_5_report.pdf`](module_5_report.pdf)

## Layout

```
module_5/
├── src/                      # application code
│   ├── flask_app.py          # create_app factory, routes, input validation
│   ├── query_data.py         # composed, parameterised reporting SQL
│   ├── load_data.py          # composed INSERT, schema helpers
│   ├── db.py                 # DB_* / DATABASE_URL resolution
│   ├── models.py             # SQLAlchemy ORM mapping
│   ├── orm_queries.py        # ORM report
│   ├── scrape.py             # ETL extract
│   ├── clean.py              # ETL transform
│   └── fields.py             # shared field names
├── tests/                    # 291 tests, all marked, 100% coverage
├── db/least_privilege.sql    # the role, its grants and the rationale
├── docs/                     # Sphinx project
├── .env.example              # variable names, no secrets
├── .pylintrc                 # three documented deviations from the defaults
├── setup.py                  # installable package
├── dependency.svg            # pydeps + Graphviz
├── snyk-analysis.png         # dependency scan evidence
├── snyk-code-analysis.png    # SAST scan evidence (extra credit)
├── ci_success.png            # green CI run
├── pylint_report.txt         # 10.00/10 evidence
├── coverage_summary.txt
├── module_5_report.pdf
├── requirements.txt          # abstract dependencies
├── requirements.lock         # resolved pins for `uv pip sync`
└── pytest.ini
```

## Fresh install

Requires Python 3.10+, PostgreSQL 14+, and Graphviz (`brew install graphviz`
or `apt-get install graphviz`) for the dependency graph.

### Option A: pip + venv

```bash
git clone git@github.com:lukeellman21/jhu_software_concepts.git
cd jhu_software_concepts/module_5
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install -e .                 # installable package, see setup.py
```

### Option B: uv

`uv pip sync` makes the environment *match* the file exactly, removing anything
not listed. That is what makes it reproducible rather than merely installable,
but it also means it needs a **fully resolved lockfile**, not the abstract
`requirements.txt`: `sync` installs exactly what is listed and does not resolve
transitive dependencies. `requirements.lock` is that resolved file, regenerated
with `uv pip compile requirements.txt -o requirements.lock`.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh    # if uv is not installed
cd jhu_software_concepts/module_5
uv venv
source .venv/bin/activate
uv pip sync requirements.lock      # exact, reproducible
uv pip install -e .
```

To resolve from the abstract file instead, use `uv pip install -r
requirements.txt`, which behaves like pip and pulls transitive dependencies.

Either way, verify:

```bash
python -c "import src; print('ok')"
pytest                            # 291 passed, 100% coverage
```

## Configuration

No credentials live in the source. The application reads the discrete
variables first and falls back to a single URL:

| Variable | Purpose |
| --- | --- |
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | preferred form; keeps the password out of any URL that might be logged |
| `DATABASE_URL` | single-string fallback, used when the `DB_*` variables are unset |
| `TEST_DATABASE_URL` | throwaway database for the test suite (default `postgresql://localhost/gradcafe_test`) |
| `GRADCAFE_DATA_FILE` | JSON dataset read by the loader |
| `FLASK_SECRET_KEY` | Flask session key; random per process when unset |

```bash
cp .env.example .env     # then fill in real values
```

`.env` is in `.gitignore` and is never committed. `.env.example` carries the
variable names and placeholder values only.

### Database setup

```bash
createdb gradcafe
createdb gradcafe_test
psql -d gradcafe -f db/least_privilege.sql \
     -v app_password="'<choose-a-password>'"
```

That script creates `gradcafe_app`: `NOSUPERUSER`, `NOCREATEDB`,
`NOCREATEROLE`, with `USAGE` on `public` and exactly `SELECT` and `INSERT` on
`applicants`. Verified behaviour under that role:

| Operation | Result |
| --- | --- |
| `GET /analysis`, every reporting query | works |
| `POST /pull-data` inserting new rows | works |
| `DROP TABLE` / `ALTER TABLE` / `CREATE TABLE` | denied |
| `UPDATE` / `DELETE` | denied |
| reading `pg_authid` | denied |

Schema creation is deliberately an administrator task: `ensure_schema()` checks
whether the table exists before issuing any DDL, so the application never needs
`CREATE` at runtime.

## Run the app

```bash
python -m src.load_data --reset      # load the bundled sample dataset
flask --app src.flask_app:create_app run
```

Open <http://127.0.0.1:5000/analysis>.

| Route | Method | Behaviour |
| --- | --- | --- |
| `/` | GET | redirect to `/analysis` |
| `/analysis` | GET | analysis page; accepts `q`, `sort`, `dir` and `limit`, all validated |
| `/pull-data` | POST | `200 {"ok": true}`; `409 {"busy": true}` while a pull runs; `500` on loader failure |
| `/update-analysis` | POST | `200 {"ok": true}`; `409` when busy; `503` when the database is unreachable |
| `/status` | GET | JSON pipeline state |

## Security tooling

### Pylint (10.00/10)

```bash
cd module_5
python -m pylint src
```

Output ends with `Your code has been rated at 10.00/10`; the captured run is in
[`pylint_report.txt`](pylint_report.txt). CI enforces it with
`python -m pylint src --fail-under=10`.

`.pylintrc` contains three documented deviations from the defaults, each for a
false positive rather than a real finding: `generated-members` for SQLAlchemy's
dynamic `func.*`, `max-args=6` for a function whose extra arguments are
keyword-only, and `min-similarity-lines=8` because two modules share six short
domain field names. The single inline `disable` is on
`src/orm_queries.py`, where SQLAlchemy generates `func.avg` dynamically and
Pylint cannot see that it is callable; `func.count` is imported as a concrete
class instead, so only one exemption remains.

### Dependency graph

```bash
python -m pydeps src --noshow -T svg -o dependency.svg --cluster --max-bacon=2
```

### Snyk

```bash
snyk auth
snyk test --file=requirements.txt --package-manager=pip     # dependencies
snyk code test                                              # SAST (extra credit)
```

### Tests

```bash
pytest module_5                                                     # from the repo root
pytest module_5 -m "web or buttons or analysis or db or integration"
```

Every test carries one of the markers `web`, `buttons`, `analysis`, `db` or
`integration`. `tests/test_sql_safety.py` covers the Module 5 hardening
specifically: the limit clamp, the identifier allow-list, parameter binding
against six injection payloads, and the environment-driven credentials.

## SQL injection defenses

Every statement is a composed `psycopg.sql` object, built separately from the
values it binds:

- **No raw string SQL.** No f-string, `+` concatenation or `.format()` on SQL
  text anywhere in `src/`.
- **Identifiers via `sql.Identifier`.** Table and column names are quoted by
  psycopg. The only user-influenced identifier is the sort column, which is
  additionally checked against the `ROW_KEYS` allow-list before composition, so
  an unknown name falls back to `p_id` instead of reaching the database.
- **Values via placeholders.** Every user value is bound with
  `sql.Placeholder()` and passed to `cursor.execute(statement, params)`. The
  SQL text is byte-for-byte identical no matter what the user sends; only the
  parameters change, which is what `test_the_sql_text_is_identical_whatever_the_user_sends`
  asserts.
- **`LIMIT` everywhere.** Every statement ends in `LIMIT %s`, and
  `clamp_limit()` forces the value into 1..100. A request for a million rows
  returns 100.
- **Wildcards escaped.** `escape_like()` escapes `%`, `_` and backslash so a
  search for `%` matches a literal percent sign rather than every row.
