from flask import Blueprint, jsonify, request, render_template, current_app
from flask_login import login_required, current_user
from sqlalchemy import desc
from app import db
from app.models import Resume, Job, JobMatch
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

    profile = current_user.profile
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

    jobs = Job.query.order_by(desc(Job.posted_date)).limit(limit).all()
    if not jobs:
        return jsonify({'error': 'No jobs in database'}), 400

    profile = current_user.profile
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
    resume_ids = [r.id for r in Resume.query.filter_by(user_id=current_user.id).all()]
    if not resume_ids:
        return jsonify([])

    matches = (JobMatch.query
               .filter(JobMatch.resume_id.in_(resume_ids))
               .filter(JobMatch.match_score >= min_score)
               .order_by(desc(JobMatch.match_score))
               .limit(limit).all())

    result = []
    for m in matches:
        job = m.job
        result.append({
            'match_id':       m.id,
            'match_score':    m.match_score,
            'matched_skills': m.matched_skills,
            'missing_skills': m.missing_skills,
            'recommendation': m.recommendation,
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
