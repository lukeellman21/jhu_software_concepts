Testing guide
=============

Running the suite
-----------------

.. code-block:: bash

   # from the repository root
   pytest module_4

   # the whole suite, selected by marker
   pytest module_4 -m "web or buttons or analysis or db or integration"

   # one slice
   pytest module_4 -m buttons

``pytest.ini`` enables coverage on every run and fails the build below 100%:

.. code-block:: ini

   [pytest]
   addopts = -q --cov=module_4/src --cov=src --cov-report=term-missing --cov-fail-under=100
   testpaths = tests
   markers =
       web: Flask route/page tests
       buttons: "Pull Data" and "Update Analysis" behavior
       analysis: formatting/rounding of analysis output
       db: database schema/inserts/selects
       integration: end-to-end flows

Both ``--cov`` paths name the same package: ``module_4/src`` resolves when the
suite is run from the repository root, ``src`` when it is run from inside
``module_4``.

Markers
-------

Every test carries at least one marker; there are no unmarked tests, so
``pytest -m "web or buttons or analysis or db or integration"`` runs the whole
suite.

.. list-table::
   :header-rows: 1
   :widths: 18 32 50

   * - Marker
     - File
     - Covers
   * - ``web``
     - ``tests/test_flask_page.py``
     - the factory, the route table, page rendering and selectors
   * - ``buttons``
     - ``tests/test_buttons.py``
     - both POST endpoints, busy gating, the error path, ``PullState``
   * - ``analysis``
     - ``tests/test_analysis_format.py``
     - ``Answer:`` labels and two-decimal percentages
   * - ``db``
     - ``tests/test_db_insert.py``, ``tests/test_db_layer.py``
     - schema, inserts, idempotency, the query functions, the ORM
   * - ``integration``
     - ``tests/test_integration_end_to_end.py``, ``tests/test_etl.py``
     - pull → update → render, repeated pulls, the ETL stages

Test database
-------------

Database tests run against a real PostgreSQL instance named by
``TEST_DATABASE_URL`` (default ``postgresql://localhost/gradcafe_test``).  The
``database_url`` fixture exports that value as ``DATABASE_URL`` for the
duration of the session, so application defaults resolve to the test database
and your own ``DATABASE_URL`` is never touched.  Create it once:

.. code-block:: bash

   createdb gradcafe_test

Fixtures
--------

.. list-table::
   :header-rows: 1
   :widths: 24 76

   * - Fixture
     - What it gives you
   * - ``database_url``
     - session-scoped connection string for the test database; exits with a
       clear message if it cannot be reached
   * - ``conn``
     - an open psycopg connection whose ``applicants`` table has just been
       dropped and recreated
   * - ``empty_db``
     - asserts the table is empty, for tests that describe a before/after
   * - ``records``
     - four raw scraped records with distinct result URLs
   * - ``make_app``
     - factory calling :func:`src.flask_app.create_app`; pass any service to
       override just that one
   * - ``app`` / ``client`` / ``state``
     - application wired to the real test database with a fake scraper
   * - ``stub_services`` / ``stub_app`` / ``stub_client``
     - every service replaced by a double, so no database is needed

Test doubles
------------

``tests/helpers.py`` holds the doubles:

``Recorder``
    A callable that records its calls and then returns ``result`` (delegating
    if ``result`` is itself callable) or raises ``error``.  Used as the fake
    scraper, loader, analysis provider, page-source provider and even as a
    ``time.sleep`` spy.

``raw_records()``
    Four deep-copied raw records covering the interesting shapes: an
    international PhD acceptance, an American PhD acceptance, an American
    Masters rejection, and a waitlisted entry with no term, origin or scores.

``survey_page_html()`` / ``survey_row()``
    Build Grad Café-shaped markup so the parser can be tested without the
    network.

Selectors
---------

UI assertions use BeautifulSoup against stable ``data-testid`` hooks rather
than CSS classes or copy:

.. list-table::
   :header-rows: 1
   :widths: 32 68

   * - Selector
     - Element
   * - ``data-testid="pull-data-btn"``
     - the **Pull Data** button
   * - ``data-testid="update-analysis-btn"``
     - the **Update Analysis** button
   * - ``data-testid="analysis-list"``
     - the list of questions
   * - ``data-testid="analysis-item"``
     - one question; also carries ``data-key`` naming the analysis key
   * - ``data-testid="analysis-answer"``
     - the ``Answer: ...`` line
   * - ``data-testid="recent-rows"``
     - the most-recently-loaded table
   * - ``data-testid="pull-status"`` / ``analysis-status``
     - the two status lines
   * - ``data-testid="pull-error"``
     - error banner, rendered only after a failed pull
   * - ``data-testid="db-error"``
     - banner shown only when PostgreSQL is unreachable

Percentages are asserted with ``re.compile(r"\d+(?:,\d{3})*(?:\.(\d+))?%")``:
every match must capture exactly two decimal digits.

Determinism
-----------

* No test reaches the network or launches a browser.
* No test calls ``sleep()`` to wait for the busy state.  The flag is a plain
  attribute on :class:`src.flask_app.PullState`, so a test sets
  ``state.begin_pull()`` and asserts the 409 directly.
* The one background-runner test captures the thread the runner returns and
  joins it.
* The full suite runs in about a second.
