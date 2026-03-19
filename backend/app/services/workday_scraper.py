"""
Workday Scraper Service
Scrapes job listings from Workday-powered career pages using Playwright.
Workday is a JS-heavy ATS that requires browser automation.

Usage:
    scraper = WorkdayScraper()
    jobs = scraper.scrape('https://apple.wd5.myworkdayjobs.com/en-US/apple_store_apl', limit=20)
"""
import re
from typing import List, Dict, Any, Optional
from datetime import datetime

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False


# Curated list of known Workday companies with their board URLs
WORKDAY_COMPANIES = {
    'apple':       'https://apple.wd5.myworkdayjobs.com/en-US/apple_store_apl',
    'microsoft':   'https://microsoft.wd1.myworkdayjobs.com/en-US/External',
    'amazon':      'https://amazon.jobs/en/search?base_url=jobs.amazon.com',
    'meta':        'https://www.metacareers.com/jobs',
    'ibm':         'https://careers.ibm.com/jobs/search',
    'salesforce':  'https://salesforce.wd1.myworkdayjobs.com/en-US/External_Career_Site',
    'workday':     'https://workday.wd5.myworkdayjobs.com/en-US/Workday',
    'adobe':       'https://adobe.wd5.myworkdayjobs.com/en-US/external_experienced',
    'oracle':      'https://eeho.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/jobsearch',
    'intel':       'https://jobs.intel.com/en/search-jobs',
}


class WorkdayScraper:
    """Playwright-based scraper for Workday career pages."""

    def __init__(self, headless: bool = True):
        self.headless = headless

    def scrape(self, base_url: str, company_name: str = 'Unknown',
               query: str = '', limit: int = 20) -> List[Dict[str, Any]]:
        """
        Scrape jobs from a Workday career board URL.
        Returns list of normalised job dicts.
        """
        if not HAS_PLAYWRIGHT:
            print('[WorkdayScraper] Playwright not installed — cannot scrape Workday.')
            return []

        jobs: List[Dict[str, Any]] = []
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=self.headless)
                context = browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                               'AppleWebKit/537.36 (KHTML, like Gecko) '
                               'Chrome/122.0.0.0 Safari/537.36'
                )
                page = context.new_page()

                try:
                    page.goto(base_url, timeout=30000, wait_until='domcontentloaded')
                    page.wait_for_timeout(3000)

                    # If query provided, try to find search box
                    if query:
                        try:
                            search_box = page.locator(
                                'input[placeholder*="search" i], '
                                'input[aria-label*="search" i], '
                                'input[type="search"]'
                            ).first
                            if search_box.is_visible(timeout=3000):
                                search_box.fill(query)
                                search_box.press('Enter')
                                page.wait_for_timeout(2000)
                        except Exception:
                            pass  # Search not available — scrape all

                    # Collect jobs from current page and up to 3 more pages
                    for page_num in range(4):
                        found = self._extract_jobs_from_page(page, company_name)
                        jobs.extend(found)

                        if len(jobs) >= limit:
                            break

                        # Try to go to next page
                        try:
                            next_btn = page.locator(
                                'button[aria-label*="next" i], '
                                'a[aria-label*="next" i], '
                                '[data-automation-id="next"] '
                            ).first
                            if next_btn.is_visible(timeout=2000) and next_btn.is_enabled():
                                next_btn.click()
                                page.wait_for_timeout(2500)
                            else:
                                break
                        except Exception:
                            break

                except PlaywrightTimeoutError:
                    print(f'[WorkdayScraper] Timeout loading {base_url}')
                finally:
                    browser.close()

        except Exception as e:
            print(f'[WorkdayScraper] Error: {e}')

        return self._deduplicate(jobs[:limit])

    def _extract_jobs_from_page(self, page, company_name: str) -> List[Dict[str, Any]]:
        """Extract job cards from the current page state."""
        jobs = []

        # Try multiple common Workday selectors
        card_selectors = [
            'li[class*="job"]',
            'li[data-automation-id*="Job"]',
            'div[data-automation-id*="Job"]',
            'section[data-automation-id="jobResults"] li',
            'ul[role="list"] li',
            '[class*="jobPosting"]',
        ]

        cards = None
        for sel in card_selectors:
            try:
                cards = page.locator(sel)
                if cards.count() > 0:
                    break
            except Exception:
                continue

        if not cards or cards.count() == 0:
            return []

        count = min(cards.count(), 25)
        for i in range(count):
            try:
                card = cards.nth(i)
                title_el = card.locator(
                    'a[data-automation-id*="jobDetail"], '
                    'a[href*="/jobs/"], h3, a'
                ).first
                title = title_el.inner_text(timeout=2000).strip()
                href  = title_el.get_attribute('href') or ''
                url   = href if href.startswith('http') else f'https://workday.com{href}'

                location = ''
                for loc_sel in ['dd[data-automation-id="location"]', '[class*="location"]', 'span:nth-child(2)']:
                    try:
                        loc_el = card.locator(loc_sel).first
                        if loc_el.count() > 0:
                            location = loc_el.inner_text(timeout=1000).strip()
                            break
                    except Exception:
                        pass

                if title and len(title) > 5:
                    jobs.append({
                        'external_id':     f'workday_{hash(url or title) & 0xFFFFFF}',
                        'title':           title,
                        'company':         company_name,
                        'location':        location or 'See posting',
                        'description':     '',
                        'required_skills': [],
                        'salary_min':      0,
                        'salary_max':      0,
                        'job_type':        'full-time',
                        'remote_type':     'remote' if 'remote' in location.lower() else 'onsite',
                        'source':          'workday',
                        'url':             url,
                        'posted_date':     datetime.utcnow(),
                    })
            except Exception:
                continue

        return jobs

    def scrape_company(self, company_slug: str,
                       query: str = '', limit: int = 20) -> List[Dict[str, Any]]:
        """Scrape a known company by slug."""
        slug = company_slug.lower().strip()
        if slug not in WORKDAY_COMPANIES:
            return []
        base_url     = WORKDAY_COMPANIES[slug]
        company_name = slug.replace('-', ' ').title()
        return self.scrape(base_url, company_name=company_name, query=query, limit=limit)

    def _deduplicate(self, jobs: List[Dict]) -> List[Dict]:
        seen = set()
        result = []
        for j in jobs:
            key = j.get('external_id', j.get('title', ''))
            if key not in seen:
                seen.add(key)
                result.append(j)
        return result
