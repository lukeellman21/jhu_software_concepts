Troubleshooting
===============

``Cannot reach the test database at postgresql://localhost/gradcafe_test``
--------------------------------------------------------------------------

The suite refuses to run without its throwaway database.  Create it, or point
``TEST_DATABASE_URL`` somewhere else:

.. code-block:: bash

   createdb gradcafe_test
   # or
   export TEST_DATABASE_URL=postgresql://user:pass@localhost:5432/other_db

``Coverage failure: total of 0 is less than fail-under=100``
------------------------------------------------------------

Coverage measured nothing, which usually means the run happened from a
directory where neither ``--cov`` path resolves.  Run ``pytest module_4`` from
the repository root, or ``pytest`` from inside ``module_4``.

``connection to server on socket ... failed``
---------------------------------------------

PostgreSQL is not running.  On macOS with Homebrew:

.. code-block:: bash

   brew services start postgresql@16
   pg_isready

``ModuleNotFoundError: No module named 'src'``
-----------------------------------------------

``module_4/conftest.py`` puts ``module_4`` on ``sys.path``; it must exist and
the run must be inside the ``module_4`` rootdir.  Outside pytest, run modules
from ``module_4`` with ``python -m src.load_data`` rather than
``python src/load_data.py``.

``psycopg.errors.NotNullViolation``
-----------------------------------

A row reached the database without passing through
:func:`src.load_data.normalize_record` -- that function is what guarantees the
required fields.  Call :func:`src.load_data.insert_rows` with the default
``normalize=True``, or normalise the rows yourself first.

The page shows stale numbers after a pull
------------------------------------------

That is the documented behaviour: press **Update Analysis**, which recomputes
the snapshot.  See :doc:`operations`.

CI: the Postgres service is up but the tests cannot connect
------------------------------------------------------------

The workflow maps the container's 5432 to the runner's 5432 and waits on
``pg_isready`` before running pytest.  Confirm ``TEST_DATABASE_URL`` points at
``localhost:5432`` and matches the ``POSTGRES_USER`` / ``POSTGRES_PASSWORD`` /
``POSTGRES_DB`` in the service block.

Selenium fails locally
----------------------

Only a live scrape needs Chrome; no test does.  If ``python -m src.scrape``
cannot start a driver, install Google Chrome -- Selenium 4 downloads the
matching driver itself.
