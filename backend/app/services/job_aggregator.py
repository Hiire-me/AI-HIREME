"""
Job Aggregator Service
Fetches real jobs from:
  1. Adzuna REST API      (free tier — https://developer.adzuna.com/)
  2. Remotive API         (open access — https://remotive.com/api/remote-jobs)
  3. Lever Job Board API  (public per-company endpoint, no key needed)
  4. Greenhouse Job Board API (public per-company endpoint, no key needed)

Lever/Greenhouse are open ATS portals — any company that uses these
platforms publishes their jobs publicly. We query a curated list of
tech companies by default, or any company slug the user passes in.
"""
import os
import hashlib
import requests
from typing import List, Dict, Any, Optional
from datetime import datetime
import re


# ─── Default company slugs to scrape ────────────────────────────────
# These are companies known to use Lever / Greenhouse publicly
_LEVER_COMPANIES_DEFAULT = [
    'netflix', 'stripe', 'notion', 'figma', 'linear',
    'vercel', 'airtable', 'cloudflare', 'discord', 'rippling',
]
_GREENHOUSE_COMPANIES_DEFAULT = [
    'shopify', 'airbnb', 'dropbox', 'lyft', 'reddit',
    'github', 'hashicorp', 'segment', 'brex', 'databricks',
]


class JobAggregator:
    ADZUNA_BASE   = "https://api.adzuna.com/v1/api/jobs"
    REMOTIVE_BASE = "https://remotive.com/api/remote-jobs"
    LEVER_BASE    = "https://api.lever.co/v0/postings/{company}?mode=json"
    GREENHOUSE_BASE = "https://boards-api.greenhouse.io/v1/boards/{company}/jobs?content=true"

    def __init__(self, adzuna_app_id: str = '', adzuna_app_key: str = '',
                 lever_companies: Optional[List[str]] = None,
                 greenhouse_companies: Optional[List[str]] = None):
        self.adzuna_id  = adzuna_app_id  or os.getenv('ADZUNA_APP_ID',  '')
        self.adzuna_key = adzuna_app_key or os.getenv('ADZUNA_APP_KEY', '')
        self.lever_companies      = lever_companies      or _LEVER_COMPANIES_DEFAULT
        self.greenhouse_companies = greenhouse_companies or _GREENHOUSE_COMPANIES_DEFAULT
        self.headers = {'User-Agent': 'AutoJobAgent/1.0', 'Accept': 'application/json'}

    # ─────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────

    def fetch_all(self, query: str = 'software developer',
                  location: str = 'remote',
                  max_per_source: int = 20,
                  sources: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Fetch from all configured sources and deduplicate."""
        enabled = sources or ['adzuna', 'remotive', 'lever', 'greenhouse']
        jobs: List[Dict[str, Any]] = []

        if 'adzuna' in enabled and self.adzuna_id and self.adzuna_key:
            jobs += self._fetch_adzuna(query, location, max_per_source)

        if 'remotive' in enabled:
            jobs += self._fetch_remotive(query, max_per_source)

        if 'lever' in enabled:
            for company in self.lever_companies[:5]:   # cap at 5 companies
                jobs += self._fetch_lever(company, query, max_per_source // 5 + 2)

        if 'greenhouse' in enabled:
            for company in self.greenhouse_companies[:5]:  # cap at 5 companies
                jobs += self._fetch_greenhouse(company, query, max_per_source // 5 + 2)

        return self._deduplicate(jobs)

    def fetch_lever(self, company_slug: str, query: str = '',
                    limit: int = 25) -> List[Dict[str, Any]]:
        """Fetch from a specific Lever company board."""
        return self._fetch_lever(company_slug, query, limit)

    def fetch_greenhouse(self, company_slug: str, query: str = '',
                         limit: int = 25) -> List[Dict[str, Any]]:
        """Fetch from a specific Greenhouse company board."""
        return self._fetch_greenhouse(company_slug, query, limit)

    # ─────────────────────────────────────────────────────────────────
    # Adzuna
    # ─────────────────────────────────────────────────────────────────

    def _fetch_adzuna(self, query: str, location: str, limit: int) -> List[Dict]:
        country = 'gb'
        url = f"{self.ADZUNA_BASE}/{country}/search/1"
        params = {
            'app_id':           self.adzuna_id,
            'app_key':          self.adzuna_key,
            'results_per_page': min(limit, 50),
            'what':             query,
            'where':            location,
            'content-type':     'application/json',
        }
        try:
            r = requests.get(url, params=params, headers=self.headers, timeout=10)
            r.raise_for_status()
            return [self._normalise_adzuna(j) for j in r.json().get('results', [])]
        except Exception as e:
            print(f"[Aggregator] Adzuna error: {e}")
            return []

    def _normalise_adzuna(self, raw: Dict) -> Dict:
        company  = raw.get('company', {}).get('display_name', 'Unknown')
        location = raw.get('location', {}).get('display_name', '')
        try:
            posted_dt = datetime.fromisoformat(raw.get('created', '').rstrip('Z'))
        except Exception:
            posted_dt = datetime.utcnow()
        return {
            'external_id':     f"adzuna_{raw.get('id', '')}",
            'title':           raw.get('title', 'Unknown'),
            'company':         company,
            'location':        location,
            'description':     raw.get('description', ''),
            'required_skills': [],
            'salary_min':      int(raw.get('salary_min', 0) or 0),
            'salary_max':      int(raw.get('salary_max', 0) or 0),
            'job_type':        'full-time',
            'remote_type':     'remote' if 'remote' in location.lower() else 'onsite',
            'source':          'adzuna',
            'url':             raw.get('redirect_url', ''),
            'posted_date':     posted_dt,
        }

    # ─────────────────────────────────────────────────────────────────
    # Remotive
    # ─────────────────────────────────────────────────────────────────

    def _fetch_remotive(self, query: str, limit: int) -> List[Dict]:
        try:
            r = requests.get(self.REMOTIVE_BASE, params={'search': query, 'limit': limit},
                             headers=self.headers, timeout=10)
            r.raise_for_status()
            return [self._normalise_remotive(j) for j in r.json().get('jobs', [])[:limit]]
        except Exception as e:
            print(f"[Aggregator] Remotive error: {e}")
            return []

    def _normalise_remotive(self, raw: Dict) -> Dict:
        tags = raw.get('tags', []) or []
        try:
            posted_dt = datetime.fromisoformat(raw.get('publication_date', '').rstrip('Z'))
        except Exception:
            posted_dt = datetime.utcnow()
        jtype = (raw.get('job_type') or 'full_time').replace('_', '-')
        return {
            'external_id':     f"remotive_{raw.get('id', '')}",
            'title':           raw.get('title', 'Unknown'),
            'company':         raw.get('company_name', 'Unknown'),
            'location':        raw.get('candidate_required_location', 'Remote'),
            'description':     raw.get('description', ''),
            'required_skills': tags,
            'salary_min':      0,
            'salary_max':      0,
            'job_type':        jtype,
            'remote_type':     'remote',
            'source':          'remotive',
            'url':             raw.get('url', ''),
            'posted_date':     posted_dt,
        }

    # ─────────────────────────────────────────────────────────────────
    # Lever (Public ATS — no auth needed)
    # ─────────────────────────────────────────────────────────────────

    def _fetch_lever(self, company: str, query: str, limit: int) -> List[Dict]:
        """
        Lever public API: GET https://api.lever.co/v0/postings/{company}?mode=json
        Returns all open roles for that company. Free, no API key needed.
        """
        url = self.LEVER_BASE.format(company=company.lower().strip())
        try:
            r = requests.get(url, headers=self.headers, timeout=10)
            r.raise_for_status()
            postings = r.json()
            if not isinstance(postings, list):
                return []

            # Filter by query if provided
            q = query.lower()
            if q:
                postings = [p for p in postings
                            if q in p.get('text', '').lower()
                            or q in p.get('categories', {}).get('team', '').lower()
                            or q in (p.get('description', '') or '').lower()]

            return [self._normalise_lever(p, company) for p in postings[:limit]]
        except Exception as e:
            print(f"[Aggregator] Lever ({company}) error: {e}")
            return []

    def _normalise_lever(self, raw: Dict, company: str) -> Dict:
        # Lever response fields
        categories = raw.get('categories', {}) or {}
        location   = categories.get('location', '') or raw.get('workplaceType', 'Remote')
        team       = categories.get('team', '')
        jtype      = (categories.get('commitment') or 'Full-time').replace('_', ' ')

        # Description comes as HTML — strip tags simply
        desc_html  = raw.get('descriptionPlain', '') or raw.get('description', '')
        desc       = re.sub(r'<[^>]+>', ' ', desc_html).strip()[:3000]

        # Timestamp
        ts = raw.get('createdAt', 0)
        try:
            posted_dt = datetime.utcfromtimestamp(ts / 1000) if ts > 1e9 else datetime.utcnow()
        except Exception:
            posted_dt = datetime.utcnow()

        # Tags as skills
        tags = raw.get('tags', []) or []

        company_name = company.replace('-', ' ').title()
        apply_url    = raw.get('applyUrl') or f"https://jobs.lever.co/{company}/{raw.get('id', '')}"

        return {
            'external_id':     f"lever_{raw.get('id', '')}",
            'title':           raw.get('text', 'Unknown Role'),
            'company':         company_name,
            'location':        location,
            'description':     f"[{team}]\n\n{desc}" if team else desc,
            'required_skills': tags,
            'salary_min':      0,
            'salary_max':      0,
            'job_type':        jtype,
            'remote_type':     'remote' if 'remote' in location.lower() else 'hybrid',
            'source':          'lever',
            'url':             apply_url,
            'posted_date':     posted_dt,
        }

    # ─────────────────────────────────────────────────────────────────
    # Greenhouse (Public ATS — no auth needed)
    # ─────────────────────────────────────────────────────────────────

    def _fetch_greenhouse(self, company: str, query: str, limit: int) -> List[Dict]:
        """
        Greenhouse public API:
          GET https://boards-api.greenhouse.io/v1/boards/{company}/jobs?content=true
        No auth required. Returns all open roles.
        """
        url = self.GREENHOUSE_BASE.format(company=company.lower().strip())
        try:
            r = requests.get(url, headers=self.headers, timeout=10)
            r.raise_for_status()
            data = r.json()
            jobs = data.get('jobs', []) if isinstance(data, dict) else []

            # Filter by query
            q = query.lower()
            if q:
                jobs = [j for j in jobs
                        if q in j.get('title', '').lower()
                        or q in (j.get('content', '') or '').lower()]

            return [self._normalise_greenhouse(j, company) for j in jobs[:limit]]
        except Exception as e:
            print(f"[Aggregator] Greenhouse ({company}) error: {e}")
            return []

    def _normalise_greenhouse(self, raw: Dict, company: str) -> Dict:
        # Greenhouse fields
        location = raw.get('location', {}).get('name', 'Unknown') if raw.get('location') else ''
        departments = raw.get('departments', []) or []
        dept = departments[0].get('name', '') if departments else ''

        # Content (description) may be HTML
        desc_html = raw.get('content', '') or ''
        desc = re.sub(r'<[^>]+>', ' ', desc_html).strip()[:3000]

        # Updated_at
        updated = raw.get('updated_at', '')
        try:
            posted_dt = datetime.fromisoformat(updated.rstrip('Z'))
        except Exception:
            posted_dt = datetime.utcnow()

        company_name = company.replace('-', ' ').title()
        apply_url    = raw.get('absolute_url', f"https://boards.greenhouse.io/{company}")

        # Greenhouse may have metadata tags
        metadata = raw.get('metadata', []) or []
        tags = [m.get('value') for m in metadata if m.get('value') and isinstance(m.get('value'), str)]

        return {
            'external_id':     f"greenhouse_{raw.get('id', '')}",
            'title':           raw.get('title', 'Unknown Role'),
            'company':         company_name,
            'location':        location,
            'description':     f"[{dept}]\n\n{desc}" if dept else desc,
            'required_skills': tags,
            'salary_min':      0,
            'salary_max':      0,
            'job_type':        'full-time',
            'remote_type':     'remote' if 'remote' in location.lower() else 'onsite',
            'source':          'greenhouse',
            'url':             apply_url,
            'posted_date':     posted_dt,
        }

    # ─────────────────────────────────────────────────────────────────
    # Deduplication
    # ─────────────────────────────────────────────────────────────────

    def _dedup_key(self, job: Dict) -> str:
        title   = job.get('title', '').lower().strip()
        company = job.get('company', '').lower().strip()
        return hashlib.md5(f"{title}|{company}".encode()).hexdigest()

    def _deduplicate(self, jobs: List[Dict]) -> List[Dict]:
        seen: set = set()
        result: List[Dict] = []
        for job in jobs:
            key = self._dedup_key(job)
            if key not in seen:
                seen.add(key)
                result.append(job)
        return result
