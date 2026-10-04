"""Packaging for the Grad Café analytics service.

Making the project installable is what lets ``import src.query_data`` resolve
identically from the application, the test suite, Sphinx and CI, instead of
depending on which directory the interpreter happened to start in.  Install it
in editable mode during development::

    pip install -e .

``uv`` can also read this file when syncing an environment.
"""
from pathlib import Path

from setuptools import find_packages, setup

HERE = Path(__file__).parent
README = (HERE / "README.md").read_text(encoding="utf-8")

#: Runtime dependencies. Tooling (pylint, pydeps, pytest) lives in
#: requirements.txt and in the ``dev`` extra below, not here, so that a
#: production install stays lean.
INSTALL_REQUIRES = [
    "Flask>=3.0.0",
    "psycopg[binary]>=3.2.0",
    "SQLAlchemy>=2.0.28",
    "beautifulsoup4>=4.12.0",
    "selenium>=4.20.0",
]

EXTRAS_REQUIRE = {
    "dev": [
        "pytest>=8.0.0",
        "pytest-cov>=5.0.0",
        "pylint>=3.0.0",
        "pydeps>=1.12.0",
        "sphinx>=7.2.0",
        "sphinx-rtd-theme>=2.0.0",
    ],
}

setup(
    name="gradcafe-analytics",
    version="5.0.0",
    description="Grad Café admissions analytics: Flask web app, ETL and PostgreSQL reporting.",
    long_description=README,
    long_description_content_type="text/markdown",
    author="Luke Ellman",
    python_requires=">=3.10",
    packages=find_packages(include=["src", "src.*"]),
    include_package_data=True,
    package_data={"src": ["templates/*.html", "static/*.css"]},
    install_requires=INSTALL_REQUIRES,
    extras_require=EXTRAS_REQUIRE,
    entry_points={
        "console_scripts": [
            "gradcafe-load=src.load_data:main",
            "gradcafe-report=src.query_data:run_queries",
            "gradcafe-scrape=src.scrape:main",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "Framework :: Flask",
        "Topic :: Scientific/Engineering :: Information Analysis",
    ],
)
