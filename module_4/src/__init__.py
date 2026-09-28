"""Grad Café analytics service.

The package is split into three layers:

* :mod:`src.scrape` and :mod:`src.clean` -- the extract/transform half of the ETL.
* :mod:`src.load_data`, :mod:`src.query_data`, :mod:`src.models` and
  :mod:`src.orm_queries` -- the PostgreSQL persistence and reporting layer.
* :mod:`src.flask_app` -- the web layer that renders the analysis page and
  exposes the ``Pull Data`` / ``Update Analysis`` endpoints.
"""

__all__ = ["clean", "db", "flask_app", "load_data", "models", "orm_queries", "query_data", "scrape"]
