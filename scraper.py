#!/usr/bin/env python3
"""
Academic job scraper — Canada
Sources:
  1. University Affairs (universityaffairs.ca) — primary, covers most CA postings
  2. Workday API — for universities that use Workday ATS
  3. HTML careers pages — for universities with accessible static listings

Outputs jobs.json (read by the frontend).
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
    print("ERROR: pip install requests beautifulsoup4")
    sys.exit(1)

# ── Output ────────────────────────────────────────────────────────────────────

OUTPUT_FILE = "jobs.json"

# ── Match scoring ─────────────────────────────────────────────────────────────

STRONG_KEYWORDS = [
    "neuroscience", "anatomy", "kinesiology", "neuroanatomy",
    "neurological", "neural", "brain", "nervous system",
    "sensorimotor", "musculoskeletal", "neurobiology",
    "gross anatomy", "neurophysiology", "cognitive neuroscience",
    "systems neuroscience", "behavioural neuroscience",
    "behavioral neuroscience", "human anatomy", "spinal cord",
]

PARTIAL_KEYWORDS = [
    "physiology", "psychology", "statistics", "biostatistics",
    "biology", "health science", "biomechanics", "motor control",
    "rehabilitation", "exercise science", "human kinetics",
    "histology", "cell biology", "molecular biology", "motor learning",
]

POSITION_KEYWORDS = [
    "assistant professor", "associate professor", "lecturer",
    "teaching stream", "limited-term", "limited term",
    "visiting professor", "teaching faculty", "instructor",
    "sessional", "academic position", "faculty position",
    "professor of teaching", "clinical professor",
]

# ── Province mapping ──────────────────────────────────────────────────────────

PROVINCE_ABBREVS = {
    "AB": "Alberta", "BC": "British Columbia", "MB": "Manitoba",
    "NB": "New Brunswick", "NL": "Newfoundland and Labrador",
    "NS": "Nova Scotia", "NT": "Northwest Territories",
    "NU": "Nunavut", "ON": "Ontario",
    "PE": "Prince Edward Island", "QC": "Quebec",
    "SK": "Saskatchewan", "YT": "Yukon",
}

CITY_TO_PROVINCE = {
    # Ontario
    "toronto": "Ontario", "ottawa": "Ontario", "hamilton": "Ontario",
    "london": "Ontario", "kingston": "Ontario", "waterloo": "Ontario",
    "guelph": "Ontario", "windsor": "Ontario", "sudbury": "Ontario",
    "thunder bay": "Ontario", "barrie": "Ontario", "peterborough": "Ontario",
    "oshawa": "Ontario", "mississauga": "Ontario", "brampton": "Ontario",
    "markham": "Ontario", "st. catharines": "Ontario", "north bay": "Ontario",
    "sault ste. marie": "Ontario", "brantford": "Ontario",
    "niagara falls": "Ontario", "cambridge": "Ontario", "oakville": "Ontario",
    "burlington": "Ontario", "timmins": "Ontario", "belleville": "Ontario",
    "st catharines": "Ontario", "scarborough": "Ontario",
    # British Columbia
    "vancouver": "British Columbia", "victoria": "British Columbia",
    "burnaby": "British Columbia", "kelowna": "British Columbia",
    "surrey": "British Columbia", "abbotsford": "British Columbia",
    "richmond": "British Columbia", "prince george": "British Columbia",
    "kamloops": "British Columbia", "nanaimo": "British Columbia",
    "chilliwack": "British Columbia", "langley": "British Columbia",
    "north vancouver": "British Columbia", "new westminster": "British Columbia",
    "penticton": "British Columbia", "squamish": "British Columbia",
    # Quebec
    "montreal": "Quebec", "québec": "Quebec", "quebec city": "Quebec",
    "laval": "Quebec", "sherbrooke": "Quebec", "gatineau": "Quebec",
    "trois-rivières": "Quebec", "trois-rivieres": "Quebec",
    "saguenay": "Quebec", "longueuil": "Quebec",
    # Alberta
    "calgary": "Alberta", "edmonton": "Alberta", "red deer": "Alberta",
    "lethbridge": "Alberta", "medicine hat": "Alberta",
    "grande prairie": "Alberta", "fort mcmurray": "Alberta",
    # Saskatchewan
    "saskatoon": "Saskatchewan", "regina": "Saskatchewan",
    "prince albert": "Saskatchewan", "moose jaw": "Saskatchewan",
    # Manitoba
    "winnipeg": "Manitoba", "brandon": "Manitoba",
    # New Brunswick
    "moncton": "New Brunswick", "fredericton": "New Brunswick",
    "saint john": "New Brunswick", "bathurst": "New Brunswick",
    # Nova Scotia
    "halifax": "Nova Scotia", "sydney": "Nova Scotia",
    "truro": "Nova Scotia", "wolfville": "Nova Scotia",
    "antigonish": "Nova Scotia", "dartmouth": "Nova Scotia",
    # PEI
    "charlottetown": "Prince Edward Island",
    # Newfoundland
    "st. john's": "Newfoundland and Labrador",
    "st johns": "Newfoundland and Labrador",
    "corner brook": "Newfoundland and Labrador",
    # Territories
    "yellowknife": "Northwest Territories",
    "whitehorse": "Yukon",
    "iqaluit": "Nunavut",
}

# ── University sources ────────────────────────────────────────────────────────
# Each entry must have: name, province, type ("workday" | "html")
# Workday entries need: tenant (and optionally ver)
# HTML entries need: urls (list of fallback URLs to try)

UNIVERSITY_SOURCES = [
    # ── Workday universities ──────────────────────────────────────────────────
    # Tenant names verified from known Workday career site URLs.
    # If a tenant resolves to 404, the scraper silently skips it.
    {
        "name": "McMaster University",
        "province": "Ontario",
        "type": "workday",
        "tenant": "mcmaster",
        "ver": "wd5",
    },
    {
        "name": "Western University",
        "province": "Ontario",
        "type": "workday",
        "tenant": "uwo",
        "ver": "wd3",
    },
    {
        "name": "University of Waterloo",
        "province": "Ontario",
        "type": "workday",
        "tenant": "uwaterloo",
        "ver": "wd3",
    },
    {
        "name": "Queen's University",
        "province": "Ontario",
        "type": "workday",
        "tenant": "queensu",
        "ver": "wd5",
    },
    {
        "name": "Carleton University",
        "province": "Ontario",
        "type": "workday",
        "tenant": "carleton",
        "ver": "wd5",
    },
    {
        "name": "York University",
        "province": "Ontario",
        "type": "workday",
        "tenant": "yorkuniversity",
        "ver": "wd5",
    },
    {
        "name": "University of Guelph",
        "province": "Ontario",
        "type": "workday",
        "tenant": "uguelph",
        "ver": "wd5",
    },
    {
        "name": "University of Calgary",
        "province": "Alberta",
        "type": "workday",
        "tenant": "ucalgary",
        "ver": "wd5",
    },
    {
        "name": "University of Alberta",
        "province": "Alberta",
        "type": "workday",
        "tenant": "ualberta",
        "ver": "wd5",
    },
    {
        "name": "University of Manitoba",
        "province": "Manitoba",
        "type": "workday",
        "tenant": "umanitoba",
        "ver": "wd5",
    },
    {
        "name": "University of Saskatchewan",
        "province": "Saskatchewan",
        "type": "workday",
        "tenant": "usask",
        "ver": "wd5",
    },
    {
        "name": "University of British Columbia",
        "province": "British Columbia",
        "type": "workday",
        "tenant": "ubc",
        "ver": "wd10",
    },
    {
        "name": "Simon Fraser University",
        "province": "British Columbia",
        "type": "workday",
        "tenant": "sfu",
        "ver": "wd5",
    },
    {
        "name": "Memorial University",
        "province": "Newfoundland and Labrador",
        "type": "workday",
        "tenant": "mun",
        "ver": "wd5",
    },
    {
        "name": "Dalhousie University",
        "province": "Nova Scotia",
        "type": "workday",
        "tenant": "dal",
        "ver": "wd3",
    },
    # ── HTML careers pages ────────────────────────────────────────────────────
    # These universities either don't use Workday or have accessible static listings.
    {
        "name": "University of Toronto",
        "province": "Ontario",
        "type": "html",
        "urls": [
            "https://jobs.utoronto.ca/faculty-and-librarians-staff",
            "https://jobs.utoronto.ca/",
        ],
    },
    {
        "name": "University of Ottawa",
        "province": "Ontario",
        "type": "html",
        "urls": [
            "https://hr.uottawa.ca/en/careers",
            "https://uottawa.njoyn.com/cl2/xweb/Xweb.asp?clid=57917&page=joblisting",
        ],
    },
    {
        "name": "University of Victoria",
        "province": "British Columbia",
        "type": "html",
        "urls": [
            "https://www.uvic.ca/hr/careers/",
            "https://www.uvic.ca/hr/careers/faculty/index.php",
        ],
    },
    {
        "name": "McGill University",
        "province": "Quebec",
        "type": "html",
        "urls": [
            "https://www.mcgill.ca/hr/career/academic-staff-employment-opportunities",
            "https://www.mcgill.ca/hr/career/",
        ],
    },
    {
        "name": "Concordia University",
        "province": "Quebec",
        "type": "html",
        "urls": ["https://www.concordia.ca/hr/dept/talent-acquisition/careers.html"],
    },
    {
        "name": "Toronto Metropolitan University",
        "province": "Ontario",
        "type": "html",
        "urls": ["https://www.torontomu.ca/careers/faculty-positions/"],
    },
    {
        "name": "Brock University",
        "province": "Ontario",
        "type": "html",
        "urls": ["https://brocku.ca/human-resources/careers/faculty-positions/"],
    },
    {
        "name": "University of New Brunswick",
        "province": "New Brunswick",
        "type": "html",
        "urls": ["https://www.unb.ca/hr/careers/"],
    },
    {
        "name": "University of Lethbridge",
        "province": "Alberta",
        "type": "html",
        "urls": ["https://www.ulethbridge.ca/hr/jobs/academic"],
    },
    {
        "name": "Wilfrid Laurier University",
        "province": "Ontario",
        "type": "html",
        "urls": ["https://www.wlu.ca/careers/"],
    },
    {
        "name": "University of Northern BC",
        "province": "British Columbia",
        "type": "html",
        "urls": ["https://www.unbc.ca/people/human-resources/career-opportunities/faculty"],
    },
    {
        "name": "Trent University",
        "province": "Ontario",
        "type": "html",
        "urls": ["https://www.trentu.ca/hr/careers/"],
    },
]

# Search terms used for Workday API and UA scraper
SEARCH_TERMS = [
    "neuroscience",
    "anatomy",
    "kinesiology",
    "neuroanatomy",
    "physiology lecturer",
    "neuroscience professor",
    "anatomy professor",
    "kinesiology professor",
]

# ── Headers ───────────────────────────────────────────────────────────────────

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
}

AJAX_HEADERS = {
    **BROWSER_HEADERS,
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "X-Requested-With": "XMLHttpRequest",
}

WORKDAY_HEADERS = {
    **BROWSER_HEADERS,
    "Accept": "application/json",
    "Content-Type": "application/json",
}

# ── Helper functions ──────────────────────────────────────────────────────────

def get_province(location_text: str) -> str:
    if not location_text:
        return "Unknown"
    text = location_text.strip()
    # Province abbreviation: "Toronto, ON" or "ON, Canada"
    for abbrev, name in PROVINCE_ABBREVS.items():
        if re.search(rf'\b{abbrev}\b', text):
            return name
    lower = text.lower()
    for full_name in PROVINCE_ABBREVS.values():
        if full_name.lower() in lower:
            return full_name
    for city, province in CITY_TO_PROVINCE.items():
        if city in lower:
            return province
    return "Unknown"


def score_match(title: str, description: str = "") -> str:
    text = (title + " " + description).lower()
    if any(kw in text for kw in STRONG_KEYWORDS):
        return "strong"
    if any(kw in text for kw in PARTIAL_KEYWORDS):
        return "partial"
    return "none"


def is_relevant_position(title: str) -> bool:
    lower = title.lower()
    return any(kw in lower for kw in POSITION_KEYWORDS)


def parse_deadline(text: str):
    if not text:
        return None
    patterns = [
        r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b',
        r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?\s+\d{1,2},?\s+\d{4}\b',
        r'\b\d{4}-\d{2}-\d{2}\b',
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(0).strip()
    return None


def make_job(title, institution, location, province, url, source,
             deadline=None, apply_url=None, date_posted=""):
    return {
        "title": title,
        "institution": institution,
        "location": location,
        "province": province or get_province(location),
        "deadline": deadline,
        "url": url,
        "apply_url": apply_url or url,
        "match": score_match(title),
        "source": source,
        "date_posted": date_posted,
    }


# ── University Affairs (WP Job Manager AJAX) ──────────────────────────────────

UA_BASE = "https://www.universityaffairs.ca"
UA_AJAX_ENDPOINTS = [
    f"{UA_BASE}/jm-ajax/get_listings/",
    f"{UA_BASE}/wp-admin/admin-ajax.php",
]
UA_SEARCH_URL = f"{UA_BASE}/search-jobs/"


def fetch_ua_ajax(session, keywords: str, page: int = 1) -> list:
    payload = {
        "search_keywords": keywords,
        "search_location": "",
        "per_page": 50,
        "orderby": "date",
        "order": "DESC",
        "page": page,
        "show_pagination": "false",
    }
    for endpoint in UA_AJAX_ENDPOINTS:
        if "admin-ajax" in endpoint:
            payload["action"] = "job_manager_get_listings"
        try:
            resp = session.post(endpoint, data=payload, headers=AJAX_HEADERS, timeout=20)
            if resp.status_code != 200:
                continue
            data = resp.json()
            html_fragment = data.get("html", "")
            if not html_fragment:
                continue
            jobs = parse_ua_html(html_fragment, "University Affairs")
            # Paginate
            max_pages = int(data.get("max_num_pages", 1))
            if max_pages > 1 and page == 1:
                for p in range(2, min(max_pages + 1, 6)):
                    time.sleep(1.5)
                    jobs += fetch_ua_ajax(session, keywords, page=p)
            return jobs
        except Exception as e:
            print(f"     UA AJAX error ({endpoint}): {e}")
    return []


def fetch_ua_html_fallback(session, keywords: str) -> list:
    url = f"{UA_SEARCH_URL}?{urlencode({'search_keywords': keywords})}"
    try:
        resp = session.get(url, headers=BROWSER_HEADERS, timeout=20)
        if resp.status_code == 200:
            return parse_ua_html(resp.text, "University Affairs")
    except Exception as e:
        print(f"     UA HTML fallback error: {e}")
    return []


def parse_ua_html(html: str, source: str) -> list:
    soup = BeautifulSoup(html, "html.parser")
    jobs = []

    listings = (
        soup.select("li.job_listing") or
        soup.select("li.job-listing") or
        soup.select(".job_listing") or
        soup.select("article.job")
    )

    if not listings:
        # Last resort: grab any link pointing to /job/ or job-preview
        for link in soup.select('a[href*="/job/"], a[href*="job-preview"], a[href*="job_id="]'):
            title = link.get_text(strip=True)
            href = link.get("href", "")
            if not href.startswith("http"):
                href = urljoin(UA_BASE, href)
            if title and is_relevant_position(title):
                jobs.append(make_job(title, "", "", "Unknown", href, source))
        return jobs

    for item in listings:
        title_el = (
            item.select_one("h3") or item.select_one(".job-title") or
            item.select_one(".position h3") or item.select_one("h2")
        )
        title = title_el.get_text(strip=True) if title_el else ""

        link_el = item.select_one("a[href]")
        url = link_el["href"] if link_el else ""
        if url and not url.startswith("http"):
            url = urljoin(UA_BASE, url)

        # Institution (strip nested location text)
        company_el = (
            item.select_one(".company-name") or item.select_one(".company") or
            item.select_one(".employer")
        )
        institution = ""
        if company_el:
            clone = BeautifulSoup(str(company_el), "html.parser")
            for el in clone.select(".location, .meta"):
                el.decompose()
            institution = clone.get_text(strip=True)

        loc_el = (
            item.select_one(".location") or item.select_one(".job-location") or
            item.select_one("li.location")
        )
        location = re.sub(r'^[\W]+', '', loc_el.get_text(strip=True)).strip() if loc_el else ""

        if title:
            jobs.append(make_job(title, institution, location,
                                  get_province(location), url, source))
    return jobs


# ── Workday API scraper ───────────────────────────────────────────────────────

WORKDAY_VERSIONS = ["wd5", "wd10", "wd3", "wd1"]


def fetch_workday(session, name: str, tenant: str, province: str, preferred_ver: str = "wd5") -> list:
    """Search a Workday-based university career portal via its undocumented JSON API."""
    versions_to_try = [preferred_ver] + [v for v in WORKDAY_VERSIONS if v != preferred_ver]
    jobs = []

    for ver in versions_to_try:
        base = f"https://{tenant}.{ver}.myworkday.com"
        search_url = f"{base}/wday/cxs/{tenant}/jobs/search"
        headers = {
            **WORKDAY_HEADERS,
            "Origin": base,
            "Referer": f"{base}/{tenant}/d/task/",
        }

        success = False
        for term in SEARCH_TERMS:
            payload = {
                "appliedFacets": {},
                "limit": 20,
                "offset": 0,
                "searchText": term,
            }
            try:
                resp = session.post(search_url, json=payload, headers=headers, timeout=15)
                if resp.status_code == 404:
                    break  # wrong version, try next
                if resp.status_code not in (200, 201):
                    continue

                data = resp.json()
                postings = data.get("jobPostings", [])
                success = True

                for p in postings:
                    title = p.get("title", "")
                    if not title or not is_relevant_position(title):
                        continue
                    ext_path = p.get("externalPath", "")
                    job_url = f"{base}{ext_path}" if ext_path else base
                    location_text = p.get("locationsText", province)
                    jobs.append(make_job(
                        title=title,
                        institution=name,
                        location=location_text,
                        province=get_province(location_text) or province,
                        url=job_url,
                        source=name,
                        date_posted=p.get("postedOn", ""),
                    ))

                time.sleep(0.8)

            except Exception as e:
                print(f"     Workday {name} ({ver}, '{term}'): {e}")
                continue

        if success:
            break  # found working version

    if jobs:
        print(f"  ✓ {name}: {len(jobs)} jobs via Workday")
    else:
        print(f"  ✗ {name}: Workday API unreachable or no results")

    return jobs


# ── HTML careers page scraper ─────────────────────────────────────────────────

ALL_SUBJECT_KW = STRONG_KEYWORDS + PARTIAL_KEYWORDS


def fetch_html_careers(session, name: str, province: str, urls: list) -> list:
    """Scrape a university careers page. Tries each URL in the list."""
    for url in urls:
        try:
            resp = session.get(url, headers=BROWSER_HEADERS, timeout=20, allow_redirects=True)
            if resp.status_code != 200:
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            jobs = _parse_careers_html(soup, name, province, url, source=name)

            if jobs:
                print(f"  ✓ {name}: {len(jobs)} jobs via HTML ({url})")
                return jobs

        except Exception as e:
            print(f"     HTML {name} ({url}): {e}")

    print(f"  ✗ {name}: no results from HTML scrape")
    return []


def _parse_careers_html(soup, institution: str, province: str, base_url: str, source: str) -> list:
    jobs = []
    seen = set()

    # Strategy 1: structured job list elements
    for selector in [
        ".job-listing", ".job_listing", ".job-item", ".posting",
        "li.position", "tr.job", ".career-listing", ".opportunity",
    ]:
        items = soup.select(selector)
        if not items:
            continue
        for item in items:
            link = item.select_one("a[href]")
            if not link:
                continue
            text = item.get_text(" ", strip=True)
            href = link.get("href", "")
            if not href.startswith("http"):
                href = urljoin(base_url, href)
            if href in seen:
                continue
            seen.add(href)
            title = link.get_text(strip=True) or text[:120]
            if is_relevant_position(title) or any(kw in title.lower() for kw in ALL_SUBJECT_KW):
                jobs.append(make_job(title, institution, province, province, href, source))
        if jobs:
            return jobs

    # Strategy 2: scan all links heuristically
    for link in soup.select("a[href]"):
        text = link.get_text(strip=True)
        if not (10 <= len(text) <= 200):
            continue
        href = link.get("href", "")
        if not href or href.startswith(("#", "mailto:", "tel:")):
            continue

        parent_text = (link.parent.get_text(" ", strip=True) if link.parent else "")
        combined = (text + " " + parent_text).lower()

        has_position = any(kw in combined for kw in POSITION_KEYWORDS)
        has_subject = any(kw in combined for kw in ALL_SUBJECT_KW)

        if has_position and has_subject:
            if not href.startswith("http"):
                href = urljoin(base_url, href)
            if href in seen:
                continue
            seen.add(href)
            jobs.append(make_job(text, institution, province, province, href, source))

    return jobs


# ── Job detail enrichment ─────────────────────────────────────────────────────

def enrich_job(session, job: dict) -> dict:
    """Visit the individual job page to extract deadline and confirm apply URL."""
    url = job.get("url", "")
    if not url or "myworkday.com" in url:
        # Skip Workday detail pages (JS-rendered) and missing URLs
        return job
    try:
        time.sleep(1.0)
        resp = session.get(url, headers=BROWSER_HEADERS, timeout=20)
        if resp.status_code != 200:
            return job

        soup = BeautifulSoup(resp.text, "html.parser")

        # Deadline
        deadline_text = ""
        for sel in [".job-deadline", ".deadline", "[class*='deadline']",
                    ".application-deadline", ".closing-date"]:
            el = soup.select_one(sel)
            if el:
                deadline_text = el.get_text(strip=True)
                break

        if not deadline_text:
            for el in soup.select("tr, li, p, div"):
                t = el.get_text(strip=True).lower()
                if any(k in t for k in ("deadline", "closing date", "apply by", "review date")):
                    deadline_text = el.get_text(strip=True)
                    break

        parsed = parse_deadline(deadline_text)
        if parsed:
            job["deadline"] = parsed

        # Apply URL
        for sel in ["a.apply-button", "a[class*='apply']", ".job-apply a",
                    "a[href*='apply']", ".application-link a"]:
            el = soup.select_one(sel)
            if el and el.get("href"):
                href = el["href"]
                if not href.startswith("http"):
                    href = urljoin(url, href)
                job["apply_url"] = href
                break

        # Institution (if missing)
        if not job.get("institution"):
            for sel in [".company-name", ".employer", "h2.institution"]:
                el = soup.select_one(sel)
                if el:
                    job["institution"] = el.get_text(strip=True)
                    break

    except Exception as e:
        print(f"     Enrichment failed ({url[:60]}): {e}")
    return job


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"\n[{datetime.now(timezone.utc).isoformat()}] Academic job scraper starting...\n")

    session = requests.Session()
    session.headers.update(BROWSER_HEADERS)

    # Warm-up
    try:
        session.get("https://www.universityaffairs.ca", timeout=15)
        time.sleep(1.5)
    except Exception:
        pass

    all_jobs: list[dict] = []
    seen_urls: set[str] = set()
    sources_checked: list[str] = []
    sources_successful: list[str] = []

    def add_jobs(new_jobs: list, source_name: str):
        added = 0
        for job in new_jobs:
            url = job.get("url", "")
            key = url or job.get("title", "") + job.get("institution", "")
            if key and key not in seen_urls:
                seen_urls.add(key)
                all_jobs.append(job)
                added += 1
        if added:
            sources_successful.append(source_name)
        return added

    # ── 1. University Affairs ─────────────────────────────────────────────────
    print("=" * 60)
    print("SOURCE: University Affairs")
    print("=" * 60)
    sources_checked.append("University Affairs")

    ua_total = 0
    for term in SEARCH_TERMS:
        print(f"\nSearching UA: '{term}'")
        jobs = fetch_ua_ajax(session, term)
        if not jobs:
            jobs = fetch_ua_html_fallback(session, term)
        count = add_jobs(jobs, "University Affairs")
        ua_total += count
        print(f"  → Added {count} new jobs")
        time.sleep(2)

    print(f"\nUniversity Affairs total: {ua_total} new unique jobs")

    # ── 2. University-specific sources ────────────────────────────────────────
    for uni in UNIVERSITY_SOURCES:
        name = uni["name"]
        province = uni["province"]
        src_type = uni["type"]
        sources_checked.append(name)

        print(f"\n{'=' * 60}")
        print(f"SOURCE: {name} [{src_type.upper()}]")
        print(f"{'=' * 60}")

        if src_type == "workday":
            jobs = fetch_workday(
                session, name, uni["tenant"], province,
                preferred_ver=uni.get("ver", "wd5")
            )
        elif src_type == "html":
            jobs = fetch_html_careers(session, name, province, uni["urls"])
        else:
            jobs = []

        # Position-type filter (for HTML scrapers that return raw links)
        if src_type == "html":
            jobs = [j for j in jobs if is_relevant_position(j.get("title", ""))]

        count = add_jobs(jobs, name)
        print(f"  → Added {count} new unique jobs")
        time.sleep(1.5)

    # ── 3. Filter: only relevant matches (strong or partial) ──────────────────
    print(f"\n{'=' * 60}")
    print("FILTERING & ENRICHING")
    print(f"{'=' * 60}")
    print(f"Total raw jobs before match filter: {len(all_jobs)}")

    relevant = [j for j in all_jobs if j.get("match") in ("strong", "partial")]
    print(f"After match filter: {len(relevant)}")

    # ── 4. Enrich (fetch deadlines from job detail pages) ─────────────────────
    enriched = []
    for i, job in enumerate(relevant):
        print(f"Enriching {i+1}/{len(relevant)}: {job['title'][:55]}")
        job = enrich_job(session, job)
        enriched.append(job)

    # ── 5. Sort: strong first, then by deadline ───────────────────────────────
    def sort_key(j):
        order = {"strong": 0, "partial": 1}
        return (order.get(j.get("match"), 2), j.get("deadline") or "9999")

    enriched.sort(key=sort_key)

    # ── 6. Write output ───────────────────────────────────────────────────────
    output = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "sources_checked": len(sources_checked),
        "sources_successful": len(set(sources_successful)),
        "source_names": sources_checked,
        "jobs": enriched,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Wrote {len(enriched)} jobs to {OUTPUT_FILE}")
    print(f"   Sources checked: {len(sources_checked)} | Successful: {len(set(sources_successful))}")
    print(f"   Completed at: {output['last_updated']}")


if __name__ == "__main__":
    main()
