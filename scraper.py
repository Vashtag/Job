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
import xml.etree.ElementTree as ET
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
    # Physical education / health pedagogy (e.g. UBC PE job)
    "physical education", "health pedagogy", "health promotion",
    "human performance", "exercise physiology", "sport science",
    "movement science", "health education", "physical activity",
    "health kinesiology", "applied health", "health and physical",
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
# type "workday_jobs" → myworkdayjobs.com career site API (confirmed from real URLs)
# type "html"         → HTML careers page scraping
# Note: myworkday.com entries removed — tenant names were guessed and DNS-invalid.
# All confirmed portals use myworkdayjobs.com.

UNIVERSITY_SOURCES = [
    # ── myworkdayjobs.com portals — CONFIRMED from real job URLs ─────────────

    # UBC: https://ubc.wd10.myworkdayjobs.com/ubcfacultyjobs
    {"name": "University of British Columbia", "province": "British Columbia",
     "type": "workday_jobs", "tenant": "ubc", "career_site": "ubcfacultyjobs", "ver": "wd10"},

    # Waterloo: https://uwaterloo.wd3.myworkdayjobs.com/uw_careers
    {"name": "University of Waterloo", "province": "Ontario",
     "type": "workday_jobs", "tenant": "uwaterloo", "career_site": "uw_careers", "ver": "wd3"},

    # McGill: https://mcgill.wd3.myworkdayjobs.com/McGill_Careers
    {"name": "McGill University", "province": "Quebec",
     "type": "workday_jobs", "tenant": "mcgill", "career_site": "McGill_Careers", "ver": "wd3"},

    # Ottawa: https://uottawa.wd3.myworkdayjobs.com/uOttawa_External_Career_Site
    {"name": "University of Ottawa", "province": "Ontario",
     "type": "workday_jobs", "tenant": "uottawa",
     "career_site": "uOttawa_External_Career_Site", "ver": "wd3"},

    # Brock: https://brocku.wd3.myworkdayjobs.com/brocku_careers
    {"name": "Brock University", "province": "Ontario",
     "type": "workday_jobs", "tenant": "brocku", "career_site": "brocku_careers", "ver": "wd3"},

    # ── HTML careers pages ────────────────────────────────────────────────────

    # McMaster uses PeopleSoft (not Workday)
    {"name": "McMaster University", "province": "Ontario", "type": "html",
     "urls": ["https://careers.mcmaster.ca/",
              "https://careers.mcmaster.ca/job-search-results/?category=Academic%20/%20Faculty"]},

    # Western uses PeopleSoft at recruit.uwo.ca (not Workday)
    {"name": "Western University", "province": "Ontario", "type": "html",
     "urls": ["https://recruit.uwo.ca/hr/jobs_available.htm",
              "https://uwo.ca/hr/working/faculty/index.html"]},

    {"name": "Queen's University", "province": "Ontario", "type": "html",
     "urls": ["https://careers.queensu.ca/",
              "https://www.queensu.ca/humanresources/apply-jobs"]},

    {"name": "Carleton University", "province": "Ontario", "type": "html",
     "urls": ["https://carleton.ca/hr/careers/",
              "https://carleton.ca/hr/careers/faculty-positions/"]},

    # York uses Technomedia ATS (not Workday)
    {"name": "York University", "province": "Ontario", "type": "html",
     "urls": ["https://hr.yorku.ca/careers/",
              "https://jobs-ca.technomedia.com/yorkuniversity/"]},

    {"name": "University of Guelph", "province": "Ontario", "type": "html",
     "urls": ["https://careers.uoguelph.ca/",
              "https://www.uoguelph.ca/hr/jobs"]},

    {"name": "University of Toronto", "province": "Ontario", "type": "html",
     "urls": ["https://jobs.utoronto.ca/faculty-and-librarians-staff",
              "https://jobs.utoronto.ca/"]},

    {"name": "Toronto Metropolitan University", "province": "Ontario", "type": "html",
     "urls": ["https://www.torontomu.ca/careers/faculty-positions/"]},

    {"name": "Wilfrid Laurier University", "province": "Ontario", "type": "html",
     "urls": ["https://www.wlu.ca/careers/"]},

    {"name": "Trent University", "province": "Ontario", "type": "html",
     "urls": ["https://www.trentu.ca/hr/careers/"]},

    # NOSM University (Northern Ontario School of Medicine)
    {"name": "NOSM University", "province": "Ontario", "type": "html",
     "urls": ["https://www.nosm.ca/about/administrative-offices/human-resources/work-at-nosm/",
              "https://www.nosm.ca/about/administrative-offices/human-resources/work-at-nosm/career-opportunity/"]},

    # University of Alberta uses Oracle Cloud HCM (not Workday)
    {"name": "University of Alberta", "province": "Alberta", "type": "html",
     "urls": ["https://www.ualberta.ca/en/careers.html",
              "https://www.ualberta.ca/en/human-resources/hr-for-prospective-employees/faculty-positions.html"]},

    {"name": "University of Calgary", "province": "Alberta", "type": "html",
     "urls": ["https://www.ucalgary.ca/careers",
              "https://ucalgary.ca/hr/careers/academic"]},

    {"name": "University of Lethbridge", "province": "Alberta", "type": "html",
     "urls": ["https://www.ulethbridge.ca/hr/jobs/academic"]},

    # University of Manitoba uses own portal (not Workday)
    {"name": "University of Manitoba", "province": "Manitoba", "type": "html",
     "urls": ["https://umanitoba.ca/careers/"]},

    {"name": "University of Saskatchewan", "province": "Saskatchewan", "type": "html",
     "urls": ["https://careers.usask.ca/",
              "https://careers.usask.ca/job-search-results/?category=Faculty"]},

    # UBC Faculty of Education (separate from main UBC Workday portal)
    {"name": "UBC Faculty of Education", "province": "British Columbia", "type": "html",
     "urls": ["https://educ.ubc.ca/faculty-staff/jobs-at-educ/",
              "https://educ.ubc.ca/about/jobs/"]},

    # Simon Fraser uses own HR portal (not Workday)
    {"name": "Simon Fraser University", "province": "British Columbia", "type": "html",
     "urls": ["https://www.sfu.ca/human-resources/join-SFU.html",
              "https://www.sfu.ca/human-resources/careers.html"]},

    {"name": "University of Victoria", "province": "British Columbia", "type": "html",
     "urls": ["https://www.uvic.ca/hr/careers/",
              "https://www.uvic.ca/hr/careers/faculty/index.php"]},

    {"name": "University of Northern BC", "province": "British Columbia", "type": "html",
     "urls": ["https://www.unbc.ca/people/human-resources/career-opportunities/faculty"]},

    # Memorial uses own portal (not Workday)
    {"name": "Memorial University", "province": "Newfoundland and Labrador", "type": "html",
     "urls": ["https://www.mun.ca/hr/careers/"]},

    {"name": "Dalhousie University", "province": "Nova Scotia", "type": "html",
     "urls": ["https://dal.ca/dept/hr/careers.html"]},

    {"name": "Concordia University", "province": "Quebec", "type": "html",
     "urls": ["https://www.concordia.ca/hr/dept/talent-acquisition/careers.html"]},

    {"name": "University of New Brunswick", "province": "New Brunswick", "type": "html",
     "urls": ["https://www.unb.ca/hr/careers/"]},
]

# Search terms used for Workday API and UA scraper.
# Keep short — each term = one API call per university.
SEARCH_TERMS = [
    "neuroscience",
    "anatomy",
    "kinesiology",
    "neuroanatomy",
    "physiology",
    "physical education",
    "health sciences",
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


# Fields clearly unrelated to neuroscience / kinesiology / anatomy.
# Any job whose title contains one of these gets score "none" regardless.
NEGATIVE_TITLE_KEYWORDS = [
    "mining", "petroleum", "geological engineering", "geotechnical",
    "mechanical engineering", "electrical engineering", "civil engineering",
    "chemical engineering", "nuclear engineering", "materials engineering",
    "accounting", "finance", "taxation", "auditing",
    "law school", "legal studies", "jurisprudence", "criminology",
    "dentistry", "dental hygiene", "veterinary",
    "agriculture", "agronomy", "horticulture",
    "music", "fine art", "theatre", "dance performance",
]


def score_match(title: str, description: str = "") -> str:
    """
    Score relevance of a job to the target profile (neuroscience / kinesiology / anatomy).

    Rules:
    - Any negative field keyword in the title → "none" (hard exclude)
    - Subject keyword in the TITLE → strong or partial (high confidence)
    - Subject keyword only in description (fetched page content) → one step lower
      (strong→partial, partial→partial) — search terms must NOT be passed as
      description; only pass actual fetched job-page text
    """
    title_lower = title.lower()

    # Hard exclusion: obviously irrelevant field in title
    if any(kw in title_lower for kw in NEGATIVE_TITLE_KEYWORDS):
        return "none"

    # Primary scoring from title
    if any(kw in title_lower for kw in STRONG_KEYWORDS):
        return "strong"
    if any(kw in title_lower for kw in PARTIAL_KEYWORDS):
        return "partial"

    # Secondary: subject keyword in fetched description (not search term)
    if description:
        desc_lower = description.lower()
        if any(kw in desc_lower for kw in STRONG_KEYWORDS):
            return "partial"   # downgrade: we can't see it in the title
        if any(kw in desc_lower for kw in PARTIAL_KEYWORDS):
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
             deadline=None, apply_url=None, date_posted="", description=""):
    return {
        "title": title,
        "institution": institution,
        "location": location,
        "province": province or get_province(location),
        "deadline": deadline,
        "url": url,
        "apply_url": apply_url or url,
        "match": score_match(title, description),
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


def fetch_ua_nonce(session) -> str:
    """
    WP Job Manager AJAX requires a security nonce embedded in the page.
    Without it the endpoint silently returns empty results.
    Fetch the search page and extract the nonce.
    """
    try:
        resp = session.get(UA_SEARCH_URL, headers=BROWSER_HEADERS, timeout=20)
        print(f"  → UA nonce page: HTTP {resp.status_code} ({len(resp.content)} bytes)")
        if resp.status_code != 200:
            return ""
        text = resp.text
        # WP Job Manager embeds nonce in various ways:
        for pat in [
            r'"nonce"\s*:\s*"([a-f0-9]+)"',
            r'"ajax_nonce"\s*:\s*"([a-f0-9]+)"',
            r'job_manager_nonce["\s:=]+["\']([a-f0-9]+)["\']',
            r'security["\s:=]+["\']([a-f0-9]+)["\']',
            r'wpjm_nonce["\s:=]+["\']([a-f0-9]+)["\']',
        ]:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                nonce = m.group(1)
                print(f"  → UA nonce found: {nonce[:8]}…")
                return nonce
        print("  → UA nonce not found in page (will try without)")
    except Exception as e:
        print(f"     UA nonce fetch: {e}")
    return ""


def fetch_ua_rss(session) -> list:
    """
    Try University Affairs RSS feeds.
    WP Job Manager exposes RSS at /search-jobs/feed/ (all jobs) and
    WordPress itself at /feed/?post_type=job_listing.
    We pull all jobs and filter by our keywords.
    """
    rss_urls = [
        f"{UA_BASE}/search-jobs/feed/",
        f"{UA_BASE}/feed/?post_type=job_listing",
        f"{UA_BASE}/career/feed/",
    ]
    jobs = []
    for url in rss_urls:
        try:
            resp = session.get(url, headers=BROWSER_HEADERS, timeout=15)
            print(f"  → UA RSS {url}: HTTP {resp.status_code} ({len(resp.content)} bytes)")
            if resp.status_code != 200:
                continue
            text = resp.text.strip()
            if not text.startswith("<?xml") and not text.startswith("<rss"):
                continue
            root = ET.fromstring(text)
            ns = {"content": "http://purl.org/rss/1.0/modules/content/"}
            items = root.findall(".//item")
            if not items:
                continue
            print(f"  → UA RSS: found {len(items)} items in feed")
            for item in items:
                title = item.findtext("title", "").strip()
                link  = item.findtext("link",  "").strip()
                desc  = item.findtext("description", "") or ""
                # Try encoded content for richer text
                content = item.find("content:encoded", ns)
                body = content.text if content is not None and content.text else desc
                # Filter: only keep relevant positions with matching subjects
                if not title:
                    continue
                combined = (title + " " + body).lower()
                has_subject  = any(kw in combined for kw in STRONG_KEYWORDS + PARTIAL_KEYWORDS)
                has_position = any(kw in combined for kw in POSITION_KEYWORDS)
                if not (has_subject and has_position):
                    continue
                # Try to extract institution from description
                institution = ""
                inst_match = re.search(r'<strong>([^<]+)</strong>', body)
                if inst_match:
                    institution = inst_match.group(1).strip()
                # Try to find location
                loc_match = re.search(r',\s*([A-Z]{2})\b', body)
                location = loc_match.group(0).strip(", ") if loc_match else ""
                jobs.append(make_job(
                    title=title, institution=institution, location=location,
                    province=get_province(location), url=link,
                    source="University Affairs",
                ))
            if jobs:
                print(f"  ✓ UA RSS: {len(jobs)} relevant jobs")
                return jobs
        except Exception as e:
            print(f"     UA RSS ({url}): {e}")
    return []


def fetch_ua_wp_rest(session, keyword: str) -> list:
    """
    Try WordPress REST API for University Affairs job_listing post type.
    Tries WP Job Manager v1 REST API first, then generic WP REST API.
    This bypasses the JS-rendered frontend entirely.
    """
    # WP Job Manager v2.x exposes a dedicated REST namespace
    rest_endpoints = [
        f"{UA_BASE}/wp-json/wpjm/v1/jobs",
        f"{UA_BASE}/wp-json/wp/v2/job_listing",
    ]
    params = {
        "search": keyword,
        "per_page": 100,
        "status": "publish",
        "_fields": "id,title,link,meta,excerpt",
    }
    jobs = []
    url = None
    data = None
    for endpoint in rest_endpoints:
        try:
            resp = session.get(endpoint, params=params, headers=BROWSER_HEADERS, timeout=20)
            if resp.status_code not in (200, 201):
                continue
            result = resp.json()
            # WPJM v1 returns {"jobs": [...]} or {"results": [...]}
            if isinstance(result, dict):
                data = result.get("jobs") or result.get("results") or []
            elif isinstance(result, list):
                data = result
            else:
                continue
            if data:
                url = endpoint
                print(f"  → UA WP REST: {len(data)} results from {endpoint}")
                break
        except Exception as e:
            print(f"     UA WP REST ({endpoint}): {e}")

    if not data:
        return []

    def _meta(meta, key):
        v = meta.get(key, "")
        if isinstance(v, list):
            return v[0] if v else ""
        return str(v)

    for item in data:
        raw_title = item.get("title", {})
        title = BeautifulSoup(
            raw_title.get("rendered", "") if isinstance(raw_title, dict) else str(raw_title),
            "html.parser"
        ).get_text(strip=True)
        link = item.get("link", "") or item.get("url", "")
        meta = item.get("meta", {})
        institution = _meta(meta, "_company_name") or item.get("company", {}).get("name", "")
        location    = _meta(meta, "_job_location") or item.get("location", "")
        deadline_raw = _meta(meta, "_job_expires") or _meta(meta, "_application_deadline")
        if title:
            jobs.append(make_job(
                title=title, institution=institution, location=location,
                province=get_province(location), url=link,
                source="University Affairs", deadline=parse_deadline(deadline_raw),
            ))
    return jobs


def fetch_ua_ajax(session, keywords: str, page: int = 1, nonce: str = "") -> list:
    payload = {
        "search_keywords": keywords,
        "search_location": "",
        "per_page": 50,
        "orderby": "date",
        "order": "DESC",
        "page": page,
        "show_pagination": "false",
    }
    if nonce:
        payload["security"] = nonce
    for endpoint in UA_AJAX_ENDPOINTS:
        if "admin-ajax" in endpoint:
            payload["action"] = "job_manager_get_listings"
        try:
            resp = session.post(endpoint, data=payload, headers=AJAX_HEADERS, timeout=20)
            print(f"  → UA AJAX {endpoint}: HTTP {resp.status_code} ({len(resp.content)} bytes)")
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
                    jobs += fetch_ua_ajax(session, keywords, page=p, nonce=nonce)
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
        dns_failed = False
        for term in SEARCH_TERMS:
            payload = {
                "appliedFacets": {},
                "limit": 20,
                "offset": 0,
                "searchText": term,
            }
            try:
                resp = session.post(search_url, json=payload, headers=headers, timeout=10)
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
                err = str(e)
                if "NameResolutionError" in err or "Name or service not known" in err:
                    # DNS failed → tenant subdomain doesn't exist, skip all versions
                    print(f"  ✗ {name}: tenant '{tenant}' not found in DNS — skipping")
                    dns_failed = True
                    break
                print(f"     Workday {name} ({ver}, '{term}'): {e}")
                continue

        if dns_failed:
            break  # No point trying other versions
        if success:
            break  # found working version

    if jobs:
        print(f"  ✓ {name}: {len(jobs)} jobs via Workday")
    else:
        print(f"  ✗ {name}: Workday API unreachable or no results")

    return jobs


# ── Workday Jobs site scraper (myworkdayjobs.com) ────────────────────────────
# Different URL structure from myworkday.com:
# Search: POST https://{tenant}.{ver}.myworkdayjobs.com/wday/cxs/{tenant}/{career_site}/jobs/search
# Confirmed: brocku.wd3.myworkdayjobs.com/brocku_careers


def fetch_workday_jobs_site(session, name: str, tenant: str, career_site: str,
                             province: str, ver: str = "wd3") -> list:
    """Search a Workday Jobs Portal (myworkdayjobs.com) via its JSON search API."""
    base = f"https://{tenant}.{ver}.myworkdayjobs.com"
    search_url = f"{base}/wday/cxs/{tenant}/{career_site}/jobs/search"
    headers = {
        **WORKDAY_HEADERS,
        "Origin": base,
        "Referer": f"{base}/{career_site}",
    }

    jobs = []
    seen_ids = set()
    api_reachable = False

    for term in SEARCH_TERMS:
        payload = {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": term}
        try:
            resp = session.post(search_url, json=payload, headers=headers, timeout=15)
            if resp.status_code == 404:
                print(f"  ✗ {name}: myworkdayjobs.com endpoint 404 — career_site alias may be wrong")
                break
            if resp.status_code not in (200, 201):
                continue

            data = resp.json()
            api_reachable = True
            for p in data.get("jobPostings", []):
                title = p.get("title", "")
                if not title or not is_relevant_position(title):
                    continue
                ext_path = p.get("externalPath", "")
                job_url = f"{base}{ext_path}" if ext_path else base
                if job_url in seen_ids:
                    continue
                seen_ids.add(job_url)
                loc = p.get("locationsText", province)
                jobs.append(make_job(
                    title=title, institution=name, location=loc,
                    province=get_province(loc) or province,
                    url=job_url, source=name, date_posted=p.get("postedOn", ""),
                ))
            time.sleep(0.8)

        except Exception as e:
            err = str(e)
            if "NameResolutionError" in err or "Name or service not known" in err:
                print(f"  ✗ {name}: tenant '{tenant}' not found in DNS — skipping")
                break
            print(f"     Workday Jobs {name} ('{term}'): {e}")

    if jobs:
        print(f"  ✓ {name}: {len(jobs)} jobs via myworkdayjobs.com")
    elif not api_reachable:
        print(f"  ✗ {name}: myworkdayjobs.com API unreachable")
    else:
        print(f"  ✗ {name}: API reachable but no matching positions found")

    return jobs


# ── CSBBCS job board scraper ──────────────────────────────────────────────────
# csbbcs.org (Canadian Society for Brain, Behaviour & Cognitive Science)
# maintains curated lists of Canadian neuroscience / cognitive science faculty
# positions. Pages are simple HTML — no JS rendering, no auth needed.
# Confirmed positions: StFX Neuroscience TT, Queen's Neuroscience Director,
# Cape Breton Behavioural Neuroscience LTA.

CSBBCS_PAGES = [
    ("https://www.csbbcs.org/jobs/tenure-track-positions", "Tenure-Track"),
    ("https://www.csbbcs.org/jobs/term-positions",         "Term"),
    ("https://www.csbbcs.org/jobs/crc",                    "CRC"),
]


def fetch_csbbcs(session) -> list:
    """
    Scrape CSBBCS job board pages.

    Page structure: each posting is a block of text (usually a <p> or <div>)
    containing the institution name, position description, and a link to the
    actual posting URL at the university or UA. We extract:
      - the external link as the apply URL
      - surrounding paragraph text as the job description / title source
      - institution name from "University of …" / "Université …" patterns
    """
    jobs = []
    seen_urls: set[str] = set()

    for page_url, category in CSBBCS_PAGES:
        try:
            resp = session.get(page_url, headers=BROWSER_HEADERS, timeout=20)
            print(f"  → CSBBCS {category}: HTTP {resp.status_code} ({len(resp.content)} bytes)")
            if resp.status_code != 200:
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            # Remove nav / footer / header noise
            for tag in soup.select("nav, header, footer, .navigation, .menu"):
                tag.decompose()

            # Each job entry is typically a paragraph or div containing an
            # outbound link to the full posting. Walk every block-level element.
            for block in soup.select("p, li, div.job, div.posting, article"):
                block_text = block.get_text(" ", strip=True)
                # Must look like a job announcement
                if not any(kw in block_text.lower() for kw in
                           ("applications", "position", "professor", "lecturer",
                            "instructor", "faculty", "chair")):
                    continue
                if len(block_text) < 40:
                    continue

                # Find outbound link (to the actual job posting)
                job_url = ""
                for a in block.select("a[href]"):
                    href = a.get("href", "")
                    if href.startswith("http") and "csbbcs.org" not in href:
                        job_url = href
                        break
                # If no outbound link, use the CSBBCS page itself as reference
                if not job_url:
                    # Check parent for a link
                    parent = block.parent
                    for a in (parent.select("a[href]") if parent else []):
                        href = a.get("href", "")
                        if href.startswith("http") and "csbbcs.org" not in href:
                            job_url = href
                            break
                if not job_url:
                    job_url = page_url  # fallback: CSBBCS page itself

                if job_url in seen_urls and job_url != page_url:
                    continue

                # Extract institution name
                institution = ""
                inst_match = re.search(
                    r'\b((?:University|Université|Collège|College|NOSM|École)\s+(?:of\s+)?[\w\s\-\']+?)(?:\s+(?:invites|is|seeks|Department))',
                    block_text, re.IGNORECASE
                )
                if inst_match:
                    institution = inst_match.group(1).strip()

                # Derive a concise title: first sentence up to 120 chars,
                # or try to find "rank of X" pattern
                title = ""
                rank_match = re.search(
                    r'\b((?:Assistant|Associate|Full|Adjunct|Clinical|Visiting|Adjunct|Tier\s+\d)\s+'
                    r'Professor(?:\s*,\s*Teaching\s+Stream)?'
                    r'|Lecturer|Instructor|Research\s+Chair|Canada\s+Research\s+Chair)',
                    block_text, re.IGNORECASE
                )
                subject_match = re.search(
                    r'(?:in|of|area of|expertise in)\s+([\w\s,/&\(\)-]{3,60}?)(?:\.|,|\band\b|$)',
                    block_text, re.IGNORECASE
                )
                if rank_match:
                    rank = rank_match.group(1).strip()
                    subject = subject_match.group(1).strip() if subject_match else ""
                    title = f"{rank}{', ' + subject if subject else ''}"
                    if institution:
                        title = f"{title} — {institution}"
                else:
                    # Fall back to first meaningful sentence
                    title = block_text[:120].split(".")[0].strip()

                if not title or len(title) < 10:
                    continue

                # Score against both title and block text (real content, not search term)
                match = score_match(title, block_text)
                if match == "none":
                    continue

                province = get_province(block_text)
                seen_urls.add(job_url)
                jobs.append(make_job(
                    title=title, institution=institution, location="Canada",
                    province=province or "Unknown", url=job_url,
                    source="CSBBCS", description=block_text,
                ))

        except Exception as e:
            print(f"     CSBBCS ({page_url}): {e}")

    if jobs:
        print(f"  ✓ CSBBCS: {len(jobs)} relevant jobs")
    else:
        print("  ✗ CSBBCS: 0 relevant jobs found")
    return jobs


# ── CAUT Academic Work scraper ────────────────────────────────────────────────
# academicwork.ca is CAUT's Canadian academic job board (caut.ca).
# Jobs are indexed with clean slug URLs. We try the search page + sitemap.

CAUT_BASE = "https://www.academicwork.ca"


def fetch_caut(session, term: str) -> list:
    """Scrape CAUT Academic Work search results page for a keyword."""
    search_url = f"{CAUT_BASE}/search"
    params = {"q": term}
    jobs = []
    try:
        resp = session.get(search_url, params=params, headers=BROWSER_HEADERS, timeout=20)
        print(f"  → CAUT '{term}': HTTP {resp.status_code} ({len(resp.content)} bytes)")
        if resp.status_code != 200:
            return []
        soup = BeautifulSoup(resp.text, "html.parser")

        # Try structured selectors first
        for sel in ["article.job", ".job-card", ".job-listing", "li.job", ".search-result"]:
            items = soup.select(sel)
            if items:
                for item in items:
                    link = item.select_one("a[href]")
                    if not link:
                        continue
                    title = link.get_text(strip=True) or item.get_text(" ", strip=True)[:120]
                    href = link["href"]
                    if not href.startswith("http"):
                        href = urljoin(CAUT_BASE, href)
                    if not title or href in {j["url"] for j in jobs}:
                        continue
                    # Extract institution from common sub-elements
                    inst_el = item.select_one(".institution, .university, .employer, .company")
                    institution = inst_el.get_text(strip=True) if inst_el else ""
                    loc_el = item.select_one(".location, .city, .province")
                    location = loc_el.get_text(strip=True) if loc_el else "Canada"
                    jobs.append(make_job(
                        title=title, institution=institution, location=location,
                        province=get_province(location), url=href,
                        source="CAUT Academic Work",
                    ))
                if jobs:
                    return jobs

        # No structured selectors matched — page is likely JS-rendered.
        # Do NOT fall back to scanning all /jobs/ links: that grabs every job
        # on the page regardless of whether it matched the search term.
        print(f"  → CAUT '{term}': no structured job elements found (JS-rendered?)")
    except Exception as e:
        print(f"     CAUT '{term}': {e}")
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

        # Rescore using full page text — rescues jobs where the subject keyword
        # appears in the description but not the title (e.g. Workday API results
        # where only the title was available at scrape time).
        # Only upgrade, never downgrade: a title-based "strong" stays "strong".
        if job.get("match") == "none":
            page_text = soup.get_text(" ", strip=True)
            rescored = score_match(job.get("title", ""), page_text)
            if rescored != "none":
                job["match"] = rescored
                print(f"     ↑ rescored to '{rescored}' from page text: {job['title'][:60]}")

    except Exception as e:
        print(f"     Enrichment failed ({url[:60]}): {e}")
    return job


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"\n[{datetime.now(timezone.utc).isoformat()}] Academic job scraper starting...\n")

    session = requests.Session()
    session.headers.update(BROWSER_HEADERS)

    # Warm-up — log status so we know if the site is reachable at all
    try:
        r = session.get("https://www.universityaffairs.ca", timeout=15)
        print(f"  UA warm-up: HTTP {r.status_code} ({len(r.content)} bytes)")
        time.sleep(1.5)
    except Exception as e:
        print(f"  UA warm-up FAILED: {e}")

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

    # Approach 1: RSS feed (most reliable — no JS needed)
    # Fetch nonce once — required for WP Job Manager AJAX to return results
    print("\nFetching UA security nonce...")
    ua_nonce = fetch_ua_nonce(session)
    time.sleep(1)

    # Approach 1: RSS feed (no JS, no nonce needed)
    print("\nTrying UA RSS feed...")
    rss_jobs = fetch_ua_rss(session)
    ua_total += add_jobs(rss_jobs, "University Affairs")
    time.sleep(1.5)

    # Approach 2: WordPress REST API per keyword
    print("\nTrying UA WordPress REST API...")
    for term in SEARCH_TERMS:
        rest_jobs = fetch_ua_wp_rest(session, term)
        added = add_jobs(rest_jobs, "University Affairs")
        if added:
            print(f"  WP REST '{term}': +{added}")
        ua_total += added
        time.sleep(1)

    # Approach 3: WP Job Manager AJAX with nonce
    print("\nTrying UA AJAX endpoints...")
    for term in SEARCH_TERMS:
        print(f"\nSearching UA AJAX: '{term}'")
        jobs = fetch_ua_ajax(session, term, nonce=ua_nonce)
        if not jobs:
            jobs = fetch_ua_html_fallback(session, term)
        count = add_jobs(jobs, "University Affairs")
        ua_total += count
        print(f"  → Added {count} new jobs")
        time.sleep(2)

    print(f"\nUniversity Affairs total: {ua_total} new unique jobs")

    # ── 1b. CSBBCS job board ──────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("SOURCE: CSBBCS (csbbcs.org — Canadian neuroscience job board)")
    print("=" * 60)
    sources_checked.append("CSBBCS")
    csbbcs_jobs = fetch_csbbcs(session)
    csbbcs_jobs = [j for j in csbbcs_jobs if is_relevant_position(j.get("title", ""))]
    csbbcs_total = add_jobs(csbbcs_jobs, "CSBBCS")
    print(f"CSBBCS total: {csbbcs_total} new unique jobs")
    time.sleep(1.5)

    # ── 1c. CAUT Academic Work ────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("SOURCE: CAUT Academic Work (academicwork.ca)")
    print("=" * 60)
    sources_checked.append("CAUT Academic Work")
    caut_total = 0
    for term in SEARCH_TERMS:
        caut_jobs = fetch_caut(session, term)
        # Filter to relevant positions
        caut_jobs = [j for j in caut_jobs if is_relevant_position(j.get("title", ""))]
        added = add_jobs(caut_jobs, "CAUT Academic Work")
        caut_total += added
        if added:
            print(f"  '{term}': +{added}")
        time.sleep(1.5)
    print(f"CAUT total: {caut_total} new unique jobs")

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
        elif src_type == "workday_jobs":
            jobs = fetch_workday_jobs_site(
                session, name, uni["tenant"], uni["career_site"],
                province, ver=uni.get("ver", "wd3")
            )
        elif src_type == "html":
            jobs = fetch_html_careers(session, name, province, uni["urls"])
        else:
            jobs = []

        # Position-type filter for HTML scrapers (Workday already filters)
        if src_type == "html":
            jobs = [j for j in jobs if is_relevant_position(j.get("title", ""))]

        count = add_jobs(jobs, name)
        print(f"  → Added {count} new unique jobs")
        time.sleep(1.5)

    # ── 3. Pre-enrich Workday title-only jobs so rescoring can promote them ────
    # Workday API returns only the job title — the subject keyword may only
    # appear in the full posting. Fetch those pages first, then rescore.
    print(f"\n{'=' * 60}")
    print("FILTERING & ENRICHING")
    print(f"{'=' * 60}")
    print(f"Total raw jobs before match filter: {len(all_jobs)}")

    ua_sources = {"University Affairs", "CAUT Academic Work"}
    workday_unscored = [
        j for j in all_jobs
        if j.get("match") == "none"
        and j.get("source") not in ua_sources
        and is_relevant_position(j.get("title", ""))
    ]
    if workday_unscored:
        print(f"Pre-enriching {len(workday_unscored)} Workday jobs for rescore...")
        for job in workday_unscored:
            enrich_job(session, job)   # modifies job dict in-place; may set match

    relevant = [j for j in all_jobs if j.get("match") in ("strong", "partial")]
    print(f"After match filter: {len(relevant)}")

    # ── 4. Enrich remaining relevant jobs (deadline / apply URL / institution) ─
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
