"""
AI Resume & Cover Letter Generator
Uses Google Gemini for AI generation.
Falls back to a structured template when no API key is present.
"""
import os
from typing import Dict, Any

try:
    import google.generativeai as genai
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False


class ResumeGenerator:
    def __init__(self, api_key: str = ''):
        self.api_key = api_key or os.getenv('GEMINI_API_KEY', '')
        self.model   = None
        if HAS_GEMINI and self.api_key:
            try:
                genai.configure(api_key=self.api_key)
                self.model = genai.GenerativeModel('gemini-1.5-flash')
            except Exception as e:
                print(f"[ResumeGenerator] Gemini init error: {e}")

    # ─────────────────────────────────────────────────
    # Public: generate tailored resume
    # ─────────────────────────────────────────────────

    def generate_tailored_resume(self, user_profile: Dict[str, Any],
                                  job: Dict[str, Any]) -> str:
        if self.model:
            return self._gemini_resume(user_profile, job)
        return self._template_resume(user_profile, job)

    def generate_cover_letter(self, user_profile: Dict[str, Any],
                               job: Dict[str, Any]) -> str:
        if self.model:
            return self._gemini_cover_letter(user_profile, job)
        return self._template_cover_letter(user_profile, job)

    def evaluate_resume_skills(self, user_profile: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate resume skills and suggest missing ones, purely based on the resume."""
        if self.model:
            return self._gemini_evaluate_skills(user_profile)
        return self._template_evaluate_skills(user_profile)

    # ─────────────────────────────────────────────────
    # Gemini implementations
    # ─────────────────────────────────────────────────

    def _gemini_resume(self, profile: Dict, job: Dict) -> str:
        prompt = f"""You are an ATS optimization expert and professional resume writer.
Generate a high-scoring, ATS-friendly resume in clean Markdown format.

USER PROFILE:
Name: {profile.get('full_name', 'Candidate')}
Email: {profile.get('email', '')}
Phone: {profile.get('phone', '')}
Summary: {profile.get('summary', '')}
Skills: {', '.join(profile.get('skills', []))}
Experience: {self._fmt_experience(profile.get('experience', []))}
Education: {self._fmt_education(profile.get('education', []))}

TARGET JOB:
Title: {job.get('title', '')}
Company: {job.get('company', '')}
Description: {job.get('description', '')[:1500]}

INSTRUCTIONS:
- Use ## for section headers
- Naturally weave job keywords into summary and bullet points
- Start each bullet with a strong action verb
- Add quantified results where possible
- Output ONLY the resume Markdown, no preamble text
"""
        try:
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            print(f"[ResumeGenerator] Gemini error: {e}")
            return self._template_resume(profile, job)

    def _gemini_cover_letter(self, profile: Dict, job: Dict) -> str:
        prompt = f"""You are an expert career coach. Write a compelling, personalized cover letter (250-350 words).

Candidate: {profile.get('full_name', 'Candidate')}
Skills: {', '.join(profile.get('skills', [])[:8])}
Role: {job.get('title', '')} at {job.get('company', '')}
Job Description Excerpt: {job.get('description', '')[:800]}

Instructions:
- Address "Hiring Manager"
- Opening: express genuine interest in THIS role
- Body: highlight 2-3 specific achievements matching requirements
- Closing: enthusiastic call to action
- Professional but conversational tone
Output ONLY the letter text, no preamble.
"""
        try:
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            print(f"[ResumeGenerator] Gemini cover letter error: {e}")
            return self._template_cover_letter(profile, job)

    def _gemini_evaluate_skills(self, profile: Dict) -> Dict[str, Any]:
        skills_str = ', '.join(profile.get('skills', []))
        prompt = f"""You are a senior tech recruiter and career strategist.
Analyze the following candidate's skills based on current industry trends.

Candidate Skills: {skills_str if skills_str else 'None provided'}
Candidate Summary: {profile.get('summary', '')}
Candidate Job Title / Target: {profile.get('tagline', '') or 'Tech Professional'}

Task 1: Rate existing skills. Give each provided skill a "strength/demand" score (0-100) based on how sought-after it is in the current job market for their role.
Task 2: Recommend missing skills. Suggest EXACTLY 10 top skills they should learn to advance their career, and estimate the percentage of jobs asking for them (0-100). Do NOT suggest skills they already have.

Return ONLY a valid JSON object matching this schema exactly, and nothing else (no markdown wrapping, no explanation, just raw JSON):
{{
  "evaluated_skills": [
    {{"name": "SkillName1", "score": 85}},
    {{"name": "SkillName2", "score": 70}}
  ],
  "recommended_skills": [
    {{"name": "MissingSkill1", "demand": 45, "pct": 45}},
    {{"name": "MissingSkill2", "demand": 30, "pct": 30}}
  ]
}}
"""
        try:
            response = self.model.generate_content(prompt)
            text = response.text.strip()
            if text.startswith('```json'): text = text[7:]
            if text.startswith('```'): text = text[3:]
            if text.endswith('```'): text = text[:-3]
            
            import json
            data = json.loads(text.strip())
            return data
        except Exception as e:
            print(f"[ResumeGenerator] Gemini skill eval error: {e}")
            return self._template_evaluate_skills(profile)

    # ─────────────────────────────────────────────────
    # Template fallbacks (no API key needed)
    # ─────────────────────────────────────────────────

    def _template_resume(self, profile: Dict, job: Dict) -> str:
        name   = profile.get('full_name', 'Your Name')
        email  = profile.get('email', 'email@example.com')
        phone  = profile.get('phone', '+1 555 123 4567')
        skills = profile.get('skills', ['Python', 'SQL', 'Communication'])
        exp    = profile.get('experience', [])
        edu    = profile.get('education', [])
        job_title   = job.get('title', 'Target Role')
        job_company = job.get('company', 'Your Company')

        exp_block = ""
        for e in exp[:3]:
            exp_block += f"""
**{e.get('title', 'Engineer')}** — *{e.get('company', 'Company')}*
*{e.get('start_date', '20XX')} – {e.get('end_date', 'Present')}*
- {e.get('description', 'Delivered impactful results across key projects.')}

"""

        edu_block = ""
        for ed in edu[:2]:
            edu_block += f"**{ed.get('degree','')} in {ed.get('field','')}** — {ed.get('school','')} ({ed.get('year','')})\n"

        return f"""# {name}
{email} | {phone}

---

## Professional Summary
Results-driven professional with expertise in {', '.join(skills[:4])}.
Seeking to leverage proven skills in the **{job_title}** role at **{job_company}** to drive
meaningful impact and deliver high-quality outcomes.

---

## Core Skills
{' • '.join(skills)}

---

## Professional Experience
{exp_block if exp_block else '_Add your work experience in your profile._'}

---

## Education
{edu_block if edu_block else '_Add your education in your profile._'}

---
*Resume tailored for: {job_title} @ {job_company}*
"""

    def _template_cover_letter(self, profile: Dict, job: Dict) -> str:
        name    = profile.get('full_name', 'Candidate')
        skills  = profile.get('skills', ['problem-solving', 'collaboration'])
        title   = job.get('title', 'the position')
        company = job.get('company', 'your company')

        return f"""Dear Hiring Manager,

I am writing to express my enthusiastic interest in the {title} role at {company}.
With my background in {', '.join(skills[:3])}, I am confident in my ability to make
a meaningful contribution to your team.

Throughout my career I have consistently delivered results through a combination of
technical expertise and collaborative teamwork. I am particularly drawn to {company}
because of its reputation for innovation and impact.

I would welcome the opportunity to discuss how my skills align with your needs.
Thank you for considering my application.

Sincerely,
{name}
"""

    def _template_evaluate_skills(self, profile: Dict) -> Dict[str, Any]:
        """Fallback when no API key — return empty results, never fabricate data."""
        return {'evaluated_skills': [], 'recommended_skills': []}

    # ─────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────

    def _fmt_experience(self, exp_list):
        lines = []
        for e in exp_list:
            lines.append(f"  {e.get('title','?')} at {e.get('company','?')} "
                         f"({e.get('start_date','?')} - {e.get('end_date','?')}): "
                         f"{e.get('description','')[:200]}")
        return '\n'.join(lines) or 'N/A'

    def _fmt_education(self, edu_list):
        lines = []
        for e in edu_list:
            lines.append(f"  {e.get('degree','?')} in {e.get('field','?')} "
                         f"from {e.get('school','?')} ({e.get('year','?')})")
        return '\n'.join(lines) or 'N/A'
