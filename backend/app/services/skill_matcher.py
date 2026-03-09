"""
Skill Matcher Service
- TF-IDF vectorizer + cosine similarity for semantic matching
- Direct keyword overlap scoring
- Multi-factor weighted scoring: skills(40%) + title(30%) + location(20%) + salary(10%)
"""
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from typing import Dict, List, Any
import numpy as np


class SkillMatcher:
    """Match a resume/profile against a job posting."""

    # Recommendation thresholds
    STRONG = 75
    GOOD   = 55
    CONSIDER = 35

    def __init__(self):
        self.vectorizer = TfidfVectorizer(max_features=2000, stop_words='english')

    # ─────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────

    def match(self, resume_skills: List[str], job: Dict[str, Any],
              user_profile: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Returns a full match result dict:
            match_score, matched_skills, missing_skills, recommendation, breakdown
        """
        job_skills = job.get('required_skills', [])
        if not job_skills and job.get('description'):
            job_skills = []  # Will rely on semantic matching

        # Component scores
        skills_score  = self._score_skills(resume_skills, job_skills, job.get('description', ''))
        title_score   = 50.0
        location_score= 50.0
        salary_score  = 50.0

        if user_profile:
            title_score   = self._score_title(
                user_profile.get('desired_titles', []), job.get('title', ''))
            location_score= self._score_location(
                user_profile.get('desired_locations', []),
                job.get('location', ''),
                user_profile.get('remote_preference', 'hybrid'),
                job.get('remote_type', ''))
            salary_score  = self._score_salary(
                user_profile.get('min_salary', 0),
                user_profile.get('max_salary', 0),
                job.get('salary_min'),
                job.get('salary_max'))

        # Weighted combination
        total = round(
            skills_score   * 0.40 +
            title_score    * 0.30 +
            location_score * 0.20 +
            salary_score   * 0.10, 1)

        # Matched/missing skills
        matched, missing = self._skill_lists(resume_skills, job_skills)

        # Recommendation label
        if total >= self.STRONG:
            rec = 'Strong Match'
        elif total >= self.GOOD:
            rec = 'Good Match'
        elif total >= self.CONSIDER:
            rec = 'Consider'
        else:
            rec = 'Low Match'

        return {
            'match_score':    total,
            'matched_skills': matched,
            'missing_skills': missing,
            'recommendation': rec,
            'breakdown': {
                'skills':   round(skills_score,   1),
                'title':    round(title_score,    1),
                'location': round(location_score, 1),
                'salary':   round(salary_score,   1),
            }
        }

    def batch_match(self, resume_skills: List[str],
                    jobs: List[Dict[str, Any]],
                    user_profile: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """Match one resume against multiple jobs. Returns sorted list."""
        results = []
        for job in jobs:
            result = self.match(resume_skills, job, user_profile)
            result['job_id'] = job.get('id')
            results.append(result)
        results.sort(key=lambda r: r['match_score'], reverse=True)
        return results

    # ─────────────────────────────────────────────────
    # Component scorers
    # ─────────────────────────────────────────────────

    def _score_skills(self, resume_skills: List[str],
                      job_skills: List[str],
                      job_description: str = '') -> float:
        if not resume_skills:
            return 0.0

        # 1. Direct overlap with required_skills
        rs_lower = {s.lower() for s in resume_skills}
        js_lower = {s.lower() for s in job_skills}

        if js_lower:
            direct = len(rs_lower & js_lower) / len(js_lower) * 100
        else:
            direct = 0.0

        # 2. Semantic similarity via TF-IDF against job description
        semantic = 0.0
        combined_text = job_description
        if resume_skills and combined_text:
            try:
                resume_str = ' '.join(resume_skills)
                tfidf = self.vectorizer.fit_transform([resume_str, combined_text])
                semantic = float(cosine_similarity(tfidf[0:1], tfidf[1:2])[0][0]) * 100
            except Exception:
                semantic = 0.0

        # 3. Keyword presence in description
        kw_score = 0.0
        if resume_skills and combined_text:
            desc_lower = combined_text.lower()
            hits = sum(1 for s in resume_skills if s.lower() in desc_lower)
            kw_score = (hits / max(len(resume_skills), 1)) * 100

        if js_lower:
            return direct * 0.5 + semantic * 0.3 + kw_score * 0.2
        else:
            return semantic * 0.5 + kw_score * 0.5

    def _score_title(self, desired: List[str], job_title: str) -> float:
        if not desired or not job_title:
            return 50.0
        jt = job_title.lower()
        for t in desired:
            tl = t.lower()
            if tl == jt:
                return 100.0
            if tl in jt or jt in tl:
                return 85.0
        # Keyword overlap
        d_kw = set(' '.join(desired).lower().split())
        j_kw = set(jt.split())
        overlap = len(d_kw & j_kw)
        if overlap:
            return min(60 + overlap * 10, 100)
        return 25.0

    def _score_location(self, desired: List[str], job_loc: str,
                        remote_pref: str, job_remote: str) -> float:
        rp  = (remote_pref or '').lower()
        jr  = (job_remote  or '').lower()
        if rp == 'remote' and jr == 'remote':
            return 100.0
        if rp == 'hybrid' and jr in ('hybrid', 'remote'):
            return 90.0
        if rp == 'remote' and jr != 'remote':
            return 20.0
        if not desired or not job_loc:
            return 50.0
        jl = job_loc.lower()
        for loc in desired:
            if loc.lower() in jl or jl in loc.lower():
                return 100.0
        return 40.0

    def _score_salary(self, u_min: int, u_max: int,
                      j_min: int, j_max: int) -> float:
        if not u_min or not j_min:
            return 50.0
        if j_max and j_max >= u_min:
            return 100.0 if j_min >= u_min else 80.0
        if j_min >= u_min:
            return 90.0
        gap = u_min - j_min
        return max(50 - (gap / 10000 * 10), 0)

    # ─────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────

    def _skill_lists(self, resume_skills: List[str],
                     job_skills: List[str]):
        rs = {s.lower(): s for s in resume_skills}
        js = {s.lower(): s for s in job_skills}
        matched = [js[k] for k in js if k in rs]
        missing = [js[k] for k in js if k not in rs]
        return matched, missing
