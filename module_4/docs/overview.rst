Overview and setup
==================

What the service does
---------------------

The Grad Café analytics service answers a fixed set of admissions questions
from scraped Grad Café results:

* how many entries there are, and how many are for a given term,
* what share of applicants are international,
* average GPA and GRE scores, overall and sliced by degree, term and origin,
* acceptance percentages, including the high-GPA versus low-GPA split.

Every question is declared once, as a :class:`src.query_data.AnalysisSpec`, and
that declaration drives the web page, the JSON endpoints and the command-line
report.

Requirements
------------

* Python 3.10 or newer
* PostgreSQL 14 or newer (16 is used in CI)

Install
-------

.. code-block:: bash

   git clone git@github.com:lukeellman21/jhu_software_concepts.git
   cd jhu_software_concepts
   python3 -m venv module_4/.venv
   source module_4/.venv/bin/activate
   pip install -r module_4/requirements.txt

Environment variables
---------------------

.. list-table::
   :header-rows: 1
   :widths: 25 20 55

   * - Variable
     - Default
     - Purpose
   * - ``DATABASE_URL``
     - ``postgresql://localhost/gradcafe``
     - libpq connection string used by the application, the loader and the
       query layer.  :func:`src.db.sqlalchemy_url` rewrites it to
       ``postgresql+psycopg://`` for SQLAlchemy.
   * - ``TEST_DATABASE_URL``
     - ``postgresql://localhost/gradcafe_test``
     - Throwaway database used by the test suite.  The suite never reads
       ``DATABASE_URL`` directly, so your development data is safe.
   * - ``GRADCAFE_DATA_FILE``
     - ``module_4/data/sample_applicant_data.json``
     - JSON dataset loaded by :func:`src.load_data.read_records`.
   * - ``FLASK_SECRET_KEY``
     - random per process
     - Flask session key.  Nothing is hard-coded: set it in deployment, and
       every process generates its own otherwise.

No secrets are stored in the repository; credentials belong in the connection
string you export, or in your CI secrets.

Create the databases
--------------------

.. code-block:: bash

   createdb gradcafe
   createdb gradcafe_test
   export DATABASE_URL=postgresql://localhost/gradcafe

Load some data
--------------

A 20-record sample dataset ships with the repository so that nothing needs the
network to get started:

.. code-block:: bash

   cd module_4
   python -m src.load_data --reset

``--reset`` drops and recreates the table; without it the loader is additive
and idempotent (see :doc:`operations`).

Run the application
-------------------

.. code-block:: bash

   cd module_4
   flask --app src.flask_app:create_app run --debug

Then open http://127.0.0.1:5000/analysis.  ``/`` redirects there.

Run the tests
-------------

Run the suite from the **repository root** so that the ``--cov=module_4/src``
path in ``pytest.ini`` resolves:

.. code-block:: bash

   pytest module_4

The same ``pytest.ini`` also lists ``--cov=src``, so running from inside
``module_4`` reports coverage correctly too:

.. code-block:: bash

   cd module_4 && pytest

Either way the run enforces 100% coverage of ``module_4/src``.  See
:doc:`testing` for markers and fixtures.

Build the documentation
-----------------------

.. code-block:: bash

   cd module_4
   sphinx-build -b html docs docs/_build/html
   open docs/_build/html/index.html
