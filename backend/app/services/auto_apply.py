import tempfile
import os
from typing import Dict, Any
from app.services.resume_generator import ResumeGenerator

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

class AutoApplyBot:
    def __init__(self, headless: bool = True):
        self.headless = headless
        self.resume_generator = ResumeGenerator()

    def apply_to_job(self, user_profile: Dict[str, Any], job, app_obj) -> bool:
        if not HAS_PLAYWRIGHT:
            print("[AutoApplyBot] Playwright not installed.")
            return False
            
        url = job.url
        if not url:
            return False

        # Generate cover letter
        cover_letter = app_obj.cover_letter
        if not cover_letter:
            user = profile.user
            cover_letter = self.resume_generator.generate_cover_letter({
                'full_name': user.full_name if user else 'Candidate',
                'email':     user.email    if user else '',
                'phone':     user.phone    if user else '',
                'skills':    profile.skills or [],
            }, {
                'title':       job.title,
                'company':     job.company,
                'description': job.description or '',
            })
            app_obj.cover_letter = cover_letter

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=self.headless)
                context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
                page = context.new_page()
                page.goto(url, timeout=30000)

                success = False
                if 'greenhouse.io' in url:
                    success = self._fill_greenhouse(page, user_profile, cover_letter)
                elif 'lever.co' in url:
                    success = self._fill_lever(page, user_profile, cover_letter)
                else:
                    print(f"[AutoApplyBot] Unsupported ATS URL: {url}")

                if success:
                    try:
                        submit_button = page.locator("button[type='submit'], input[type='submit']").first
                        if submit_button.is_visible():
                            submit_button.click()
                            print(f"[AutoApplyBot] Submitted application to {url}.")
                            success = True
                    except Exception as e:
                        print(f"[AutoApplyBot] Could not click submit: {e}")
                        success = False
                
                browser.close()
                return success

        except Exception as e:
            print(f"[AutoApplyBot] Error running playwright: {e}")
            return False

    def _fill_greenhouse(self, page, profile, cover_letter) -> bool:
        try:
            page.fill("input[name='job_application[first_name]']", profile.user.full_name.split()[0], timeout=5000)
            page.fill("input[name='job_application[last_name]']", " ".join(profile.user.full_name.split()[1:]) if len(profile.user.full_name.split()) > 1 else "", timeout=5000)
            page.fill("input[name='job_application[email]']", profile.user.email, timeout=5000)
            page.fill("input[name='job_application[phone]']", profile.user.phone or "", timeout=5000)
            
            # Fill cover letter if text area exists
            try:
                page.fill("textarea#cover_letter_text, textarea[name='job_application[cover_letter_text]']", cover_letter, timeout=3000)
            except PlaywrightTimeoutError:
                pass

            return True
        except Exception as e:
            print(f"[AutoApplyBot] Greenhouse fill error: {e}")
            return False

    def _fill_lever(self, page, profile, cover_letter) -> bool:
        try:
            # Lever typically has a button to show the application form or goes to a different page.
            apply_buttons = page.locator("a.postings-btn")
            if apply_buttons.count() > 0:
                apply_buttons.first.click()
                page.wait_for_load_state('networkidle')

            page.fill("input[name='name']", profile.user.full_name, timeout=5000)
            page.fill("input[name='email']", profile.user.email, timeout=5000)
            page.fill("input[name='phone']", profile.user.phone or "", timeout=5000)
            page.fill("input[name='org']", profile.experience[0].get('company', '') if profile.experience else "", timeout=5000)
            
            # Cover letter
            try:
                page.fill("textarea[name='comments']", cover_letter, timeout=3000)
            except PlaywrightTimeoutError:
                pass

            return True
        except Exception as e:
            print(f"[AutoApplyBot] Lever fill error: {e}")
            return False
