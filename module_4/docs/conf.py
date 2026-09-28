"""Sphinx configuration for the Grad Café analytics service."""
from __future__ import annotations

import os
import sys
from datetime import date

# Make ``module_4`` importable so autodoc can import the ``src`` package.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

project = "Grad Café Analytics"
author = "Luke Ellman"
copyright = f"{date.today().year}, {author}"
release = "4.0"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

html_theme = "sphinx_rtd_theme"
html_static_path = []
html_title = "Grad Café Analytics"

autodoc_member_order = "bysource"
autodoc_default_options = {
    "members": True,
    "undoc-members": True,
    "show-inheritance": True,
}
autodoc_typehints = "description"

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "flask": ("https://flask.palletsprojects.com/en/stable/", None),
    "sqlalchemy": ("https://docs.sqlalchemy.org/en/20/", None),
}

nitpicky = False
