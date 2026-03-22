from flask import Blueprint, jsonify, request, render_template, current_app
from flask_login import login_required, current_user
from sqlalchemy import desc
from collections import Counter
from app import db
from app.models import User, Resume, Job, JobMatch
from app.services.skill_matcher import SkillMatcher

bp = Blueprint('matching', __name__)
_matcher = None

def _get_matcher():
    global _matcher
    if _matcher is None:
        _matcher = SkillMatcher()
    return _matcher


@bp.route('/match')
@login_required
def match_page():
    return render_template('match.html')


@bp.route('/api/match', methods=['POST'])
@login_required
def run_match():
    """Match a single resume against a single job."""
    data      = request.get_json() or {}
    resume_id = data.get('resume_id')
    job_id    = data.get('job_id')

    if not resume_id or not job_id:
        return jsonify({'error': 'resume_id and job_id required'}), 400

    resume = Resume.query.filter_by(id=resume_id, user_id=current_user.id).first()
    if not resume:
        return jsonify({'error': 'Resume not found'}), 404

    job = Job.query.get(job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404

    user = current_user
    profile = user.profile
    user_pref = {
        'desired_titles':    profile.desired_titles    if profile else [],
        'desired_locations': profile.desired_locations if profile else [],
        'remote_preference': profile.remote_preference if profile else 'hybrid',
        'min_salary':        profile.min_salary        if profile else 0,
        'max_salary':        profile.max_salary        if profile else 0,
    } if profile else {}

    job_dict = {
        'id':              job.id,
        'title':           job.title,
        'location':        job.location,
        'remote_type':     job.remote_type,
        'required_skills': job.required_skills or [],
        'description':     job.description or '',
        'salary_min':      job.salary_min,
        'salary_max':      job.salary_max,
    }

    result = _get_matcher().match(resume.extracted_skills or [], job_dict, user_pref)

    # Upsert JobMatch record
    existing = JobMatch.query.filter_by(resume_id=resume_id, job_id=job_id).first()
    if existing:
        existing.match_score    = result['match_score']
        existing.matched_skills = result['matched_skills']
        existing.missing_skills = result['missing_skills']
        existing.recommendation = result['recommendation']
    else:
        match_obj = JobMatch(
            resume_id       = resume_id,
            job_id          = job_id,
            match_score     = result['match_score'],
            matched_skills  = result['matched_skills'],
            missing_skills  = result['missing_skills'],
            recommendation  = result['recommendation'],
        )
        db.session.add(match_obj)

    db.session.commit()
    result['job_id']    = job_id
    result['resume_id'] = resume_id
    return jsonify(result)


@bp.route('/api/match/batch', methods=['POST'])
@login_required
def batch_match():
    """Match all user resumes against all jobs (or a subset) and store results."""
    data      = request.get_json() or {}
    resume_id = data.get('resume_id')
    limit     = data.get('limit', 50)

    # Pick resume
    if resume_id:
        resumes = [Resume.query.filter_by(id=resume_id, user_id=current_user.id).first()]
    else:
        resumes = Resume.query.filter_by(user_id=current_user.id).all()

    if not resumes or resumes[0] is None:
        return jsonify({'error': 'No resumes found. Please upload a resume first.'}), 400

    jobs = Job.query.order_by(Job.posted_date.desc()).limit(limit).all()
    if not jobs:
        return jsonify({'error': 'No jobs in database'}), 400

    user = current_user
    profile = user.profile
    user_pref = {
        'desired_titles':    profile.desired_titles    if profile else [],
        'desired_locations': profile.desired_locations if profile else [],
        'remote_preference': profile.remote_preference if profile else 'hybrid',
        'min_salary':        profile.min_salary        if profile else 0,
        'max_salary':        profile.max_salary        if profile else 0,
    } if profile else {}

    matcher  = _get_matcher()
    total    = 0

    for resume in resumes:
        if not resume:
            continue
        skills = resume.extracted_skills or []

        for job in jobs:
            job_dict = {
                'id':              job.id,
                'title':           job.title,
                'location':        job.location,
                'remote_type':     job.remote_type,
                'required_skills': job.required_skills or [],
                'description':     job.description or '',
                'salary_min':      job.salary_min,
                'salary_max':      job.salary_max,
            }
            result = matcher.match(skills, job_dict, user_pref)

            existing = JobMatch.query.filter_by(resume_id=resume.id, job_id=job.id).first()
            if existing:
                existing.match_score    = result['match_score']
                existing.matched_skills = result['matched_skills']
                existing.missing_skills = result['missing_skills']
                existing.recommendation = result['recommendation']
            else:
                db.session.add(JobMatch(
                    resume_id       = resume.id,
                    job_id          = job.id,
                    match_score     = result['match_score'],
                    matched_skills  = result['matched_skills'],
                    missing_skills  = result['missing_skills'],
                    recommendation  = result['recommendation'],
                ))
            total += 1

    db.session.commit()
    return jsonify({'success': True, 'matches_computed': total})


@bp.route('/api/matches', methods=['GET'])
@login_required
def get_matches():
    """Return best matches for the current user's resumes."""
    limit     = request.args.get('limit',  20,  type=int)
    min_score = request.args.get('min_score', 0, type=float)

    # All resumes for user
    resumes = Resume.query.filter_by(user_id=current_user.id).all()
    resume_ids = [r.id for r in resumes]
    if not resume_ids:
        return jsonify([])

    matches = (JobMatch.query
               .filter(JobMatch.resume_id.in_(resume_ids))
               .filter(JobMatch.match_score >= min_score)
               .order_by(desc(JobMatch.match_score))
               .limit(limit).all())

    # Compute breakdowns for each match on the fly
    matcher = _get_matcher()
    user = current_user
    profile = user.profile if user else None
    user_pref = {
        'desired_titles':    profile.desired_titles    if profile else [],
        'desired_locations': profile.desired_locations if profile else [],
        'remote_preference': profile.remote_preference if profile else 'hybrid',
        'min_salary':        profile.min_salary        if profile else 0,
        'max_salary':        profile.max_salary        if profile else 0,
    } if profile else {}

    result = []
    for m in matches:
        job = m.job
        # Try to compute breakdown
        breakdown = {'skills': 50, 'title': 50, 'location': 50, 'salary': 50}
        try:
            resume = next((r for r in resumes if r.id == m.resume_id), None)
            if resume:
                job_dict = {
                    'id': job.id, 'title': job.title, 'location': job.location,
                    'remote_type': job.remote_type,
                    'required_skills': job.required_skills or [],
                    'description': job.description or '',
                    'salary_min': job.salary_min, 'salary_max': job.salary_max,
                }
                mr = matcher.match(resume.extracted_skills or [], job_dict, user_pref)
                breakdown = mr.get('breakdown', breakdown)
        except Exception:
            pass

        result.append({
            'match_id':       m.id,
            'match_score':    m.match_score,
            'matched_skills': m.matched_skills,
            'missing_skills': m.missing_skills,
            'recommendation': m.recommendation,
            'breakdown':      breakdown,
            'job': {
                'id':        job.id,
                'title':     job.title,
                'company':   job.company,
                'location':  job.location,
                'remote_type': job.remote_type,
                'source':    job.source,
                'url':       job.url,
            }
        })

    return jsonify(result)


@bp.route('/api/skill-score', methods=['GET'])
@login_required
def skill_score():
    """Return skills directly from the user's uploaded resume, no AI scoring or fake data."""
    user = current_user
    if not user:
        return jsonify({'skills': [], 'readiness': 0})

    # Gather skills from profile (synced from resume on upload)
    skills = list(user.profile.skills or []) if user.profile else []

    if not skills:
        # Fallback: pull directly from uploaded resumes
        resumes = Resume.query.filter_by(user_id=current_user.id).all()
        all_skills = []
        for r in resumes:
            all_skills.extend(r.extracted_skills or [])
        # Deduplicate preserving order
        seen = set()
        for s in all_skills:
            if s.lower() not in seen:
                seen.add(s.lower())
                skills.append(s)

    if not skills:
        return jsonify({'skills': [], 'readiness': 0})

    # Use AI evaluation if available (Gemini API key present), otherwise return
    # skills with no score manipulation — just report them directly from resume
    from app.services.resume_generator import ResumeGenerator
    generator = ResumeGenerator(current_app.config.get('GEMINI_API_KEY', ''))

    if generator.model:
        # AI is available: get real market scores from Gemini
        profile_dict = {
            'summary': user.profile.summary if user.profile else '',
            'tagline': user.profile.resume_extra.get('tagline', '') if user.profile and user.profile.resume_extra else '',
            'skills': skills
        }
        eval_result = generator.evaluate_resume_skills(profile_dict)
        skills_out = eval_result.get('evaluated_skills', [])
        # Ensure only skills that are actually in the resume are returned
        resume_skill_set = {s.lower() for s in skills}
        skills_out = [s for s in skills_out if s.get('name', '').lower() in resume_skill_set]
        # Any skill from resume not scored by AI — add with score 50 as neutral
        scored_names = {s.get('name', '').lower() for s in skills_out}
        for s in skills:
            if s.lower() not in scored_names:
                skills_out.append({'name': s, 'score': 50})
    else:
        # No AI: return resume skills directly with a neutral score (no random/fake data)
        skills_out = [{'name': s, 'score': 50} for s in skills]

    skills_out.sort(key=lambda x: x.get('score', 0), reverse=True)

    readiness = 0
    if skills_out:
        readiness = round(sum(s.get('score', 0) for s in skills_out) / len(skills_out))

    return jsonify({'skills': skills_out, 'readiness': readiness})


@bp.route('/api/skill-recommendations', methods=['GET'])
@login_required
def skill_recommendations():
    """Recommend skills the user should learn — only using AI when available, never fake data."""
    user = current_user
    if not user:
        return jsonify([])

    # Gather skills from profile first
    skills = list(user.profile.skills or []) if user.profile else []

    if not skills:
        # Fallback: pull directly from uploaded resumes
        resumes = Resume.query.filter_by(user_id=current_user.id).all()
        all_skills = []
        for r in resumes:
            all_skills.extend(r.extracted_skills or [])
        skills = list(dict.fromkeys(all_skills))

    if not skills:
        return jsonify([])  # No resume uploaded — return empty, no fake data

    from app.services.resume_generator import ResumeGenerator
    generator = ResumeGenerator(current_app.config.get('GEMINI_API_KEY', ''))

    if not generator.model:
        # No AI available — return empty instead of fake recommendations
        return jsonify([])

    profile_dict = {
        'summary': user.profile.summary if user.profile else '',
        'tagline': user.profile.resume_extra.get('tagline', '') if user.profile and user.profile.resume_extra else '',
        'skills': skills
    }
    eval_result = generator.evaluate_resume_skills(profile_dict)

    recs_out = eval_result.get('recommended_skills', [])
    formatted_recs = []
    for r in recs_out:
        name = r.get('name', '')
        if not name:
            continue
        # Never recommend a skill that already exists in the resume
        if name.lower() in {s.lower() for s in skills}:
            continue
        formatted_recs.append({
            'name': name,
            'demand': r.get('demand', 0),
            'pct': r.get('pct', 0)
        })

    formatted_recs.sort(key=lambda x: x['pct'], reverse=True)
    return jsonify(formatted_recs[:10])
