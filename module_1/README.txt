==================================================
JHU Software Concepts - Module 1 Personal Website
==================================================

Prerequisites:
- Python 3.10 or higher
- pip package manager

Setup & Run Instructions:
1. Navigate into the module_1 directory:
   cd module_1

2. Activate virtual environment:
   source venv/bin/activate

3. Install dependencies:
   pip install -r requirements.txt

4. Launch application:
   python run.py

5. Access in browser:
   http://localhost:8080 or http://0.0.0.0:8080

Design and Implementation Approach:
- Application Architecture: Implemented an application factory pattern in app/__init__.py to decouple configuration from runtime execution.
- Routing: Configured modular URL endpoints using Flask Blueprints (app/routes.py) handling routes for Home (/), Projects (/projects), and Contact (/contact).
- Templating: Structured Jinja2 HTML templates utilizing layout inheritance (base.html) with semantic block overrides across page views.
- Static Assets: Integrated modern responsive CSS stylesheets and optimized static image assets located in app/static/.
