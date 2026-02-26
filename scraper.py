#!/usr/bin/env python3
"""
Scraper for Canadian academic teaching job postings.
Sources: University Affairs (universityaffairs.ca)
Runs via GitHub Actions twice daily and writes jobs.json.
"""

import json
import time
import re
import sys
from datetime import datetime, timezone
from urllib.parse import urljoin, urlencode

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("ERROR: Missing dependencies. Run: pip install requests beautifulsoup4")
    sys.exit(1)

# ── Configuration ────────────────────────────────────────────────────────────

OUTPUT_FILE = "jobs.json"

BASE_URL = "https://www.universityaffairs.ca"

# University Affairs uses WP Job Manager; two AJAX endpoints to try
UA_AJAX_ENDPOINTS = [
    f"{BASE_URL}/jm-ajax/get_listings/",
    f"{BASE_URL}/wp-admin/admin-ajax.php",
]

# Fallback: direct search URL (HTML scrape)
UA_SEARCH_URL = f"{BASE_URL}/search-jobs/"

# Keywords to search for (run one query per keyword group)
SEARCH_KEYWORD_GROUPS = [
    "neuroscience anatomy",
    "kinesiology anatomy",
    "neuroanatomy",
    "neuroscience lecturer",
    "anatomy lecturer",
    "kinesiology lecturer",
    "physiology lecturer",
    "neuroscience assistant professor",
    "anatomy assistant professor",
]

# Subject keywords for match scoring
STRONG_KEYWORDS = [
    "neuroscience", "anatomy", "kinesiology", "neuroanatomy",
    "neurological", "neural", "brain", "nervous system",
    "sensorimotor", "musculoskeletal", "neurobiology",
    "gross anatomy", "neurophysiology", "cognitive neuroscience",
    "systems neuroscience", "behavioural neuroscience",
    "behavioral neuroscience", "human anatomy",
]

PARTIAL_KEYWORDS = [
    "physiology", "psychology", "statistics", "biostatistics",
    "biology", "health science", "biomechanics", "motor control",
    "rehabilitation", "exercise science", "human kinetics",
    "histology", "cell biology", "molecular biology",
]

# Position types to include
POSITION_KEYWORDS = [
    "assistant professor", "lecturer", "teaching stream",
    "limited-term", "limited term", "visiting professor",
    "associate professor", "teaching faculty", "instructor",
    "sessional", "academic position", "faculty position",
]

# Province abbreviation → full name
PROVINCE_ABBREVS = {
    "AB": "Alberta", "BC": "British Columbia", "MB": "Manitoba",
    "NB": "New Brunswick", "NL": "Newfoundland and Labrador",
    "NS": "Nova Scotia", "NT": "Northwest Territories",
    "NU": "Nunavut", "ON": "Ontario",
    "PE": "Prince Edward Island", "QC": "Quebec",
    "SK": "Saskatchewan", "YT": "Yukon",
}

# City → Province (Canadian cities)
CITY_TO_PROVINCE = {
    # Ontario
    "toronto": "Ontario", "ottawa": "Ontario", "hamilton": "Ontario",
    "london": "Ontario", "kingston": "Ontario", "waterloo": "Ontario",
    "guelph": "Ontario", "windsor": "Ontario", "sudbury": "Ontario",
    "thunder bay": "Ontario", "barrie": "Ontario", "peterborough": "Ontario",
    "oshawa": "Ontario", "mississauga": "Ontario", "brampton": "Ontario",
    "markham": "Ontario", "st. catharines": "Ontario", "north bay": "Ontario",
    "sault ste. marie": "Ontario", "brantford": "Ontario", "whitby": "Ontario",
    "timmins": "Ontario", "belleville": "Ontario", "st catharines": "Ontario",
    "niagara falls": "Ontario", "cambridge": "Ontario", "oakville": "Ontario",
    "burlington": "Ontario", "richmond hill": "Ontario", "st. thomas": "Ontario",
    "scarborough": "Ontario", "etobicoke": "Ontario",
    # British Columbia
    "vancouver": "British Columbia", "victoria": "British Columbia",
    "burnaby": "British Columbia", "kelowna": "British Columbia",
    "surrey": "British Columbia", "abbotsford": "British Columbia",
    "richmond": "British Columbia", "prince george": "British Columbia",
    "kamloops": "British Columbia", "nanaimo": "British Columbia",
    "chilliwack": "British Columbia", "langley": "British Columbia",
    "delta": "British Columbia", "north vancouver": "British Columbia",
    "west vancouver": "British Columbia", "coquitlam": "British Columbia",
    "new westminster": "British Columbia", "penticton": "British Columbia",
    "trail": "British Columbia", "nelson": "British Columbia",
    "castlegar": "British Columbia",
    # Quebec
    "montreal": "Quebec", "québec": "Quebec", "quebec city": "Quebec",
    "laval": "Quebec", "sherbrooke": "Quebec", "gatineau": "Quebec",
    "trois-rivières": "Quebec", "trois-rivieres": "Quebec",
    "saguenay": "Quebec", "lévis": "Quebec", "longueuil": "Quebec",
    # Alberta
    "calgary": "Alberta", "edmonton": "Alberta", "red deer": "Alberta",
    "lethbridge": "Alberta", "medicine hat": "Alberta",
    "grande prairie": "Alberta", "fort mcmurray": "Alberta",
    "airdrie": "Alberta", "spruce grove": "Alberta", "camrose": "Alberta",
    # Saskatchewan
    "saskatoon": "Saskatchewan", "regina": "Saskatchewan",
    "prince albert": "Saskatchewan", "moose jaw": "Saskatchewan",
    "swift current": "Saskatchewan",
    # Manitoba
    "winnipeg": "Manitoba", "brandon": "Manitoba",
    "thompson": "Manitoba", "portage la prairie": "Manitoba",
    # New Brunswick
    "moncton": "New Brunswick", "fredericton": "New Brunswick",
    "saint john": "New Brunswick", "bathurst": "New Brunswick",
    "miramichi": "New Brunswick",
    # Nova Scotia
    "halifax": "Nova Scotia", "sydney": "Nova Scotia",
    "truro": "Nova Scotia", "new glasgow": "Nova Scotia",
    "dartmouth": "Nova Scotia", "wolfville": "Nova Scotia",
    "antigonish": "Nova Scotia",
    # Prince Edward Island
    "charlottetown": "Prince Edward Island",
    "summerside": "Prince Edward Island",
    # Newfoundland and Labrador
    "st. john's": "Newfoundland and Labrador",
    "st johns": "Newfoundland and Labrador",
    "corner brook": "Newfoundland and Labrador",
    "grand falls-windsor": "Newfoundland and Labrador",
    # Territories
    "yellowknife": "Northwest Territories",
    "whitehorse": "Yukon",
    "iqaluit": "Nunavut",
}

# ── Helpers ──────────────────────────────────────────────────────────────────

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-CA,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Referer": BASE_URL,
}

AJAX_HEADERS = {
    **BROWSER_HEADERS,
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "X-Requested-With": "XMLHttpRequest",
}


def get_province(location_text: str) -> str:
    """Detect Canadian province from a location string."""
    if not location_text:
        return "Unknown"

    text = location_text.strip()

    # Try province abbreviation at end: "Toronto, ON" or "Toronto, ON, Canada"
    abbrev_match = re.search(r'\b([A-Z]{2})\b', text)
    if abbrev_match:
        abbrev = abbrev_match.group(1)
        if abbrev in PROVINCE_ABBREVS:
            return PROVINCE_ABBREVS[abbrev]

    # Try full province name in the text
    lower = text.lower()
    for full_name in PROVINCE_ABBREVS.values():
        if full_name.lower() in lower:
            return full_name

    # Try city name lookup
    for city, province in CITY_TO_PROVINCE.items():
        if city in lower:
            return province

    return "Unknown"


def score_match(title: str, description: str = "") -> str:
    """Score a job as strong, partial, or none based on subject keywords."""
    text = (title + " " + description).lower()
    for kw in STRONG_KEYWORDS:
        if kw in text:
            return "strong"
    for kw in PARTIAL_KEYWORDS:
        if kw in text:
            return "partial"
    return "none"


def is_relevant_position(title: str) -> bool:
    """Return True if the job title suggests a teaching/faculty position."""
    lower = title.lower()
    return any(kw in lower for kw in POSITION_KEYWORDS)


def parse_deadline(text: str) -> str | None:
    """Try to extract a deadline date string from arbitrary text."""
    if not text:
        return None
    # Common patterns: "January 15, 2026", "2026-01-15", "Jan 15, 2026"
    patterns = [
        r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b',
        r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?\s+\d{1,2},?\s+\d{4}\b',
        r'\b\d{4}-\d{2}-\d{2}\b',
        r'\b\d{1,2}/\d{1,2}/\d{4}\b',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(0).strip()
    return None


# ── Scraping Logic ───────────────────────────────────────────────────────────

def fetch_ua_ajax(session: requests.Session, keywords: str, page: int = 1) -> list[dict]:
    """
    Try University Affairs WP Job Manager AJAX endpoints.
    Returns a list of raw job dicts parsed from the HTML response.
    """
    payload = {
        "search_keywords": keywords,
        "search_location": "",
        "per_page": 50,
        "orderby": "date",
        "order": "DESC",
        "page": page,
        "show_pagination": "false",
    }

    jobs = []

    for endpoint in UA_AJAX_ENDPOINTS:
        # The admin-ajax endpoint needs action param
        if "admin-ajax" in endpoint:
            payload["action"] = "job_manager_get_listings"

        try:
            print(f"  → Trying AJAX endpoint: {endpoint} [{keywords}]")
            resp = session.post(endpoint, data=payload, headers=AJAX_HEADERS, timeout=20)
            print(f"     Status: {resp.status_code}")

            if resp.status_code != 200:
                continue

            data = resp.json()
            html_fragment = data.get("html", "")

            if not html_fragment:
                print("     Empty html in response")
                continue

            parsed = parse_listing_html(html_fragment)
            print(f"     Parsed {len(parsed)} jobs from AJAX HTML")
            jobs.extend(parsed)

            # Handle pagination
            max_pages = int(data.get("max_num_pages", 1))
            if max_pages > 1 and page == 1:
                for p in range(2, min(max_pages + 1, 6)):  # cap at 5 pages
                    time.sleep(1.5)
                    jobs.extend(fetch_ua_ajax(session, keywords, page=p))

            return jobs  # success, stop trying other endpoints

        except (requests.RequestException, ValueError, KeyError) as e:
            print(f"     Error: {e}")
            continue

    return jobs


def fetch_ua_html_search(session: requests.Session, keywords: str) -> list[dict]:
    """
    Fallback: scrape the University Affairs HTML search results page directly.
    """
    params = {"search_keywords": keywords, "search_location": ""}
    url = f"{UA_SEARCH_URL}?{urlencode(params)}"

    try:
        print(f"  → HTML search fallback: {url}")
        resp = session.get(url, headers=BROWSER_HEADERS, timeout=20)
        print(f"     Status: {resp.status_code}")

        if resp.status_code != 200:
            return []

        return parse_listing_html(resp.text)

    except requests.RequestException as e:
        print(f"     Error: {e}")
        return []


def parse_listing_html(html: str) -> list[dict]:
    """
    Parse job listings from WP Job Manager HTML (embedded in AJAX response or page).
    Tries multiple selector patterns to handle different plugin versions.
    """
    soup = BeautifulSoup(html, "html.parser")
    jobs = []

    # Pattern 1: Standard WP Job Manager <li class="job_listing">
    listings = soup.select("li.job_listing, li.job-listing, .job_listing")

    # Pattern 2: If no <li>, look for generic job cards
    if not listings:
        listings = soup.select(".job-card, .job-item, article.job")

    # Pattern 3: Any <a> with href containing "/job/"
    if not listings:
        links = soup.select('a[href*="/job/"], a[href*="job-preview"], a[href*="job_id="]')
        for link in links:
            job = extract_from_link(link)
            if job:
                jobs.append(job)
        return jobs

    for item in listings:
        job = {}

        # Title
        title_el = (
            item.select_one("h3") or
            item.select_one(".job-title") or
            item.select_one(".position h3") or
            item.select_one("h2")
        )
        job["title"] = title_el.get_text(strip=True) if title_el else ""

        # URL (job detail page)
        link_el = item.select_one("a[href]")
        job["url"] = link_el["href"] if link_el else ""
        if job["url"] and not job["url"].startswith("http"):
            job["url"] = urljoin(BASE_URL, job["url"])

        # Institution
        company_el = (
            item.select_one(".company-name") or
            item.select_one(".company") or
            item.select_one(".employer") or
            item.select_one("strong")
        )
        # Remove nested location text from company
        if company_el:
            company_clone = BeautifulSoup(str(company_el), "html.parser")
            for loc in company_clone.select(".location, .meta"):
                loc.decompose()
            job["institution"] = company_clone.get_text(strip=True)
        else:
            job["institution"] = ""

        # Location
        loc_el = (
            item.select_one(".location") or
            item.select_one(".job-location") or
            item.select_one("li.location")
        )
        location_raw = loc_el.get_text(strip=True) if loc_el else ""
        # Strip icon/bullet text
        location_raw = re.sub(r'^[\W]+', '', location_raw).strip()
        job["location"] = location_raw
        job["province"] = get_province(location_raw)

        # Date posted / deadline (from listing snippet — full deadline on detail page)
        date_el = item.select_one("time, .date-posted, .job-posted")
        if date_el:
            job["date_posted"] = date_el.get("datetime") or date_el.get_text(strip=True)
        else:
            job["date_posted"] = ""

        job["deadline"] = None  # filled in by fetch_job_details()

        if job["title"]:
            jobs.append(job)

    return jobs


def extract_from_link(link_el) -> dict | None:
    """Extract minimal job info from a bare <a> tag (last-resort parser)."""
    href = link_el.get("href", "")
    if not href:
        return None
    if not href.startswith("http"):
        href = urljoin(BASE_URL, href)
    text = link_el.get_text(strip=True)
    if not text:
        return None
    return {
        "title": text,
        "url": href,
        "institution": "",
        "location": "",
        "province": "Unknown",
        "date_posted": "",
        "deadline": None,
    }


def fetch_job_details(session: requests.Session, job: dict) -> dict:
    """
    Visit the individual job page to extract deadline and application URL.
    """
    url = job.get("url", "")
    if not url:
        return job

    try:
        time.sleep(1.2)  # polite delay
        resp = session.get(url, headers=BROWSER_HEADERS, timeout=20)
        if resp.status_code != 200:
            return job

        soup = BeautifulSoup(resp.text, "html.parser")

        # Deadline — look for common patterns
        deadline_text = ""
        for selector in [
            ".job-deadline", ".deadline", "[class*='deadline']",
            ".job_listing-meta .date", ".application-deadline",
        ]:
            el = soup.select_one(selector)
            if el:
                deadline_text = el.get_text(strip=True)
                break

        # If no specific element, scan meta table rows for "deadline" keyword
        if not deadline_text:
            for row in soup.select("tr, li, p, div"):
                text = row.get_text(strip=True).lower()
                if "deadline" in text or "closing date" in text or "apply by" in text:
                    deadline_text = row.get_text(strip=True)
                    break

        job["deadline"] = parse_deadline(deadline_text) or deadline_text or None

        # Application URL — look for "Apply" button or link
        for selector in [
            "a.apply-button", "a[class*='apply']", ".job-apply a",
            "a[href*='apply']", ".application-link a",
        ]:
            apply_el = soup.select_one(selector)
            if apply_el and apply_el.get("href"):
                href = apply_el["href"]
                if not href.startswith("http"):
                    href = urljoin(BASE_URL, href)
                job["apply_url"] = href
                break

        # If no institution yet, try to extract from page
        if not job.get("institution"):
            inst_el = soup.select_one(".company-name, .employer, h2.institution")
            if inst_el:
                job["institution"] = inst_el.get_text(strip=True)

        # If no province yet, try location on detail page
        if job.get("province") == "Unknown":
            for selector in [".location", ".job-location", ".meta .location"]:
                loc_el = soup.select_one(selector)
                if loc_el:
                    job["location"] = loc_el.get_text(strip=True)
                    job["province"] = get_province(job["location"])
                    break

    except requests.RequestException as e:
        print(f"     Could not fetch detail page {url}: {e}")

    return job


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print(f"[{datetime.now(timezone.utc).isoformat()}] Starting scrape...")

    session = requests.Session()
    session.headers.update(BROWSER_HEADERS)

    # Warm-up: visit main site first to get cookies / bypass simple bot checks
    try:
        print("Warming up session...")
        session.get(BASE_URL, timeout=15)
        time.sleep(2)
    except Exception as e:
        print(f"Warm-up failed (non-fatal): {e}")

    all_jobs_raw: list[dict] = []
    seen_urls: set[str] = set()

    for keyword_group in SEARCH_KEYWORD_GROUPS:
        print(f"\nSearching: '{keyword_group}'")

        # Try AJAX endpoint first
        jobs = fetch_ua_ajax(session, keyword_group)

        # Fallback to HTML search if AJAX returns nothing
        if not jobs:
            jobs = fetch_ua_html_search(session, keyword_group)

        print(f"  Found {len(jobs)} raw results")

        for job in jobs:
            url = job.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                all_jobs_raw.append(job)

        time.sleep(2)  # polite delay between keyword groups

    print(f"\nTotal unique raw jobs before filtering: {len(all_jobs_raw)}")

    # Filter to relevant positions only
    relevant = [
        j for j in all_jobs_raw
        if is_relevant_position(j.get("title", ""))
    ]
    print(f"After position-type filter: {len(relevant)}")

    # Score and enrich each job
    final_jobs = []
    for i, job in enumerate(relevant):
        print(f"\nEnriching {i+1}/{len(relevant)}: {job.get('title', '')[:60]}")
        job = fetch_job_details(session, job)
        job["match"] = score_match(job.get("title", ""), "")
        # Only include Canada positions (Unknown province is kept; filter out obvious non-Canada)
        job.setdefault("apply_url", job.get("url", ""))
        final_jobs.append(job)

    # Sort: strong matches first, then partial, then others; within each group by deadline
    def sort_key(j):
        match_order = {"strong": 0, "partial": 1, "none": 2}
        return (match_order.get(j.get("match", "none"), 2), j.get("deadline") or "9999")

    final_jobs.sort(key=sort_key)

    output = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "jobs": final_jobs,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nWrote {len(final_jobs)} jobs to {OUTPUT_FILE}")
    print(f"Scrape complete at {output['last_updated']}")


if __name__ == "__main__":
    main()
