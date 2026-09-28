Grad Café Analytics
===================

A test-driven, documented service that scrapes `The Grad Café
<https://www.thegradcafe.com/>`_ admissions results, loads them into
PostgreSQL, and serves an analysis page with two controls: **Pull Data** and
**Update Analysis**.

The project is split into three layers -- web, ETL and database -- each of
which can be run, tested and extended on its own.  Start with
:doc:`overview` to get it running, then :doc:`architecture` for how the pieces
fit together.

.. toctree::
   :maxdepth: 2
   :caption: Contents

   overview
   architecture
   api
   testing
   operations
   troubleshooting

Quick reference
---------------

===========================  ==================================================
Task                         Command
===========================  ==================================================
Install dependencies         ``pip install -r module_4/requirements.txt``
Run the app                  ``flask --app src.flask_app:create_app run``
Run the tests                ``pytest module_4``
Run one marker               ``pytest module_4 -m web``
Load the sample dataset      ``python -m src.load_data --reset``
Build these docs             ``sphinx-build -b html docs docs/_build/html``
===========================  ==================================================

Indices
-------

* :ref:`genindex`
* :ref:`modindex`
