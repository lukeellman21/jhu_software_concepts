Name: Luke Ellman (JHED: lellman1)
Module Info: Module 2 - Web Scraping & Local LLM Standardization Pipeline
Due Date: September 13, 2026

Approach
----------------------------------------------------------------------
1. Robots.txt Compliance & Ethical Scraping:
   - Verified https://www.thegradcafe.com/robots.txt prior to initiating 
     scraping. The root allows generic crawling (User-agent: * Allow: /) 
     while disallowing select commercial indexing bots.
   - Evidence is documented in screenshot.jpg placed under module_2/.
   - Enforced a polite 1.0s to 1.2s delay between consecutive page requests.

2. Web Scraping Architecture (scrape.py):
   - Implemented scrape_data(), save_data(), and load_data().
   - Managed pagination dynamically via urllib.parse (urlparse, urlencode, 
     urlunparse) using query parameters pp=250 and p=<page>.
   - Used a hybrid workflow: automated rendering was conducted with Selenium 
     Chrome using an 'eager' page-load strategy to bypass unneeded asset 
     loading and handle Cloudflare challenges cleanly.
   - Parsed rendered page source using BeautifulSoup and targeted regex 
     to capture: program name, university, degree (Masters/PhD), semester/year, 
     applicant status & decision dates, origin (US/International), GPA, 
     GRE General/Verbal/AW metrics, and applicant entry URLs.
   - Successfully scraped 30,000 raw applicant records into applicant_data.json.

3. Data Cleaning (clean.py):
   - Implemented clean_data() to sanitize applicant_data.json.
   - Stripped escaped whitespace, HTML remnants, and newline artifacts.
   - Normalized numerical GPA values to valid float ranges [0.0, 5.0] and 
     parsed composite/individual GRE scores to standard numeric scales.
   - Saved sanitized data to cleaned_data.json.

4. Local LLM Standardization (llm_hosting/app.py):
   - Deployed the bundled TinyLlama-1.1B model locally via llama-cpp-python 
     with Apple Silicon GPU layer offloading (N_GPU_LAYERS=1).
   - Standardized applicant entries against canon_universities.txt and 
     canon_programs.txt to populate 'llm-generated-program' and 
     'llm-generated-university' while retaining raw strings for traceability.
   - Implemented parallel processing via parallel_run.py across CPU cores 
     to process chunks simultaneously into llm_extend_applicant_data.json.

Known Bugs & Edge Cases
----------------------------------------------------------------------
1. Local Inference Throughput:
   - On local consumer hardware, sequential inference with a 1.1B model 
     requires ~0.75s per row. Running 8 parallel workers caused severe CPU 
     cache and memory bus contention, capping throughput at ~20 rows/min. 
     To standardize all 30,000 rows in production, batch tokenized matrix 
     multiplication (e.g., vLLM or Ollama batched inference) or asynchronous 
     worker queues with bounded thread pools should be used.
2. Condensed Label Inversions:
   - Where applicant submissions concatenated degree and major into the 
     institution field (e.g., "Speech Language Pathology Masters"), the model 
     occasionally swapped the university and program targets.
3. Acronym Ambiguity:
   - Acronyms (e.g., BUET) required strict canon anchoring to prevent 
     hallucinated expansions.

Citations & External References
----------------------------------------------------------------------
- Assisted by Claude and ChatGPT for structuring Selenium explicit wait 
  loops and regex parsing rules.
- RealPython: "Beautiful Soup: Build a Web Scraper in Python"
- Official Python 3 Documentation: urllib.parse and concurrent.futures
- Course-provided llm_hosting starter code and canonical datasets.
