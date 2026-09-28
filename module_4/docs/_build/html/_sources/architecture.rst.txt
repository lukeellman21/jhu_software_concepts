Architecture
============

Three layers, one direction of dependency: the web layer depends on the
database layer, which depends on the ETL layer's output shape.  Nothing
depends on the web layer.

.. code-block:: text

   The Grad Café
        |
        |  (1) extract            src/scrape.py
        v
   raw records  --(2) transform-->  cleaned records    src/clean.py
        |
        |  (3) normalise + load    src/load_data.py
        v
   PostgreSQL "applicants"
        |
        |  (4) query               src/query_data.py, src/models.py,
        |                          src/orm_queries.py
        v
   analysis dict --(5) render-->  GET /analysis        src/flask_app.py

Web layer
---------

``src/flask_app.py``

:func:`src.flask_app.create_app` is an application factory.  Every external
dependency is an argument with a working default:

.. list-table::
   :header-rows: 1
   :widths: 22 38 40

   * - Argument
     - Default
     - Responsibility
   * - ``scraper``
     - :func:`src.scrape.pull_new_records`
     - returns raw records
   * - ``loader``
     - :func:`src.load_data.insert_rows`
     - writes them to PostgreSQL, returns the new-row count
   * - ``analysis_provider``
     - :func:`src.query_data.get_analysis`
     - returns the analysis dict
   * - ``rows_provider``
     - :func:`src.query_data.get_recent_rows`
     - returns rows for the page's table
   * - ``runner``
     - :func:`src.flask_app.run_sync`
     - executes the pull job (:func:`src.flask_app.run_in_thread` runs it in
       the background instead)

That is what lets the test suite replace the scraper with a double and still
exercise the real loader, the real database and the real template.

Pipeline state lives in one :class:`src.flask_app.PullState` object stored in
``app.extensions["gradcafe"]``.  It is the single source of truth for the busy
flag, the last pull, the last analysis and the cached analysis snapshot, and it
is what ``GET /status`` serialises.

ETL layer
---------

``src/scrape.py``, ``src/clean.py``

:class:`src.scrape.GradCafeScraper` separates *fetching* from *parsing*.
Fetching goes through an injectable ``page_source_provider`` callable that
defaults to a Selenium Chrome session; parsing is pure string work on the HTML
that provider returns.  Tests inject canned HTML, so no test opens a browser.

:mod:`src.clean` normalises whitespace and coerces the numeric fields while
deliberately keeping the scraper's key names, so that
:func:`src.load_data.normalize_record` stays the one place where database
columns are decided.

Database layer
--------------

``src/load_data.py``, ``src/query_data.py``, ``src/models.py``, ``src/orm_queries.py``

:mod:`src.load_data` owns the ``applicants`` DDL, record normalisation and an
idempotent bulk insert.  :mod:`src.query_data` owns the reporting SQL and the
formatters.  :mod:`src.models` provides the SQLAlchemy mapping used by
:mod:`src.orm_queries`, which answers a subset of the same questions through
the ORM as a cross-check on the raw SQL.

Connection strings are resolved in exactly one place, :mod:`src.db`, from
``DATABASE_URL``.

The ``applicants`` table
------------------------

.. list-table::
   :header-rows: 1
   :widths: 30 20 50

   * - Column
     - Type
     - Notes
   * - ``p_id``
     - ``INTEGER``
     - primary key, derived from the result URL
   * - ``program``
     - ``TEXT NOT NULL``
     - ``"University - Program"`` as scraped
   * - ``comments``
     - ``TEXT NOT NULL``
     - free text from the entry
   * - ``date_added``
     - ``DATE``
     - nullable; the source is inconsistent
   * - ``url``
     - ``TEXT NOT NULL``
     - Grad Café result URL
   * - ``status``
     - ``TEXT NOT NULL``
     - normalised decision
   * - ``term``
     - ``TEXT NOT NULL``
     - e.g. ``Fall 2026``, or ``Unknown``
   * - ``us_or_international``
     - ``TEXT NOT NULL``
     - ``American`` / ``International`` / ``Unknown``
   * - ``gpa``, ``gre``, ``gre_v``, ``gre_aw``
     - ``FLOAT``
     - nullable; most entries omit them
   * - ``degree``
     - ``TEXT NOT NULL``
     - ``PhD`` / ``Masters`` / ``Other``
   * - ``llm_generated_program``
     - ``TEXT``
     - LLM-standardised program name
   * - ``llm_generated_university``
     - ``TEXT``
     - LLM-standardised university name

The columns are the Module-3 set; the only change is that the fields the
application always populates are now declared ``NOT NULL``, which turns the
loader's guarantee into a database-enforced one.
