from flask import Blueprint, jsonify, request, render_template, current_app
from flask_login import login_required, current_user
from sqlalchemy import desc
from datetime import datetime, timedelta
from app import db
from app.models import Job
from app.services.job_aggregator import JobAggregator

bp = Blueprint('jobs', __name__)
_aggregator = None

def _get_aggregator():
    global _aggregator
    if _aggregator is None:
        _aggregator = JobAggregator(
            adzuna_app_id =current_app.config.get('ADZUNA_APP_ID',  ''),
            adzuna_app_key=current_app.config.get('ADZUNA_APP_KEY', ''),
        )
    return _aggregator


@bp.route('/jobs')
@login_required
def jobs_page():
    return render_template('jobs.html')


@bp.route('/api/jobs', methods=['GET'])
@login_required
def get_jobs():
    limit   = request.args.get('limit',  50,  type=int)
    offset  = request.args.get('offset', 0,   type=int)
    query   = request.args.get('query',  '')
    jtype   = request.args.get('type',   '')
    source  = request.args.get('source', '')
    remote  = request.args.get('remote', '')
    date_f  = request.args.get('date_posted', '')

    q = Job.query

    if query:
        s = f"%{query}%"
        q = q.filter((Job.title.ilike(s)) | (Job.company.ilike(s)) | (Job.description.ilike(s)))
    if jtype:
        q = q.filter(Job.job_type.ilike(f"%{jtype}%"))
    if source:
        q = q.filter(Job.source == source)
    if remote:
        q = q.filter(Job.remote_type == remote)
    if date_f:
        cutoffs = {'24h': 1, '7d': 7, '30d': 30}
        days = cutoffs.get(date_f)
        if days:
            q = q.filter(Job.posted_date >= datetime.utcnow() - timedelta(days=days))

    total = q.count()
    jobs  = q.order_by(desc(Job.posted_date)).limit(limit).offset(offset).all()

    return jsonify({
        'total': total,
        'jobs': [{
            'id':            j.id,
            'title':         j.title,
            'company':       j.company,
            'location':      j.location,
            'job_type':      j.job_type,
            'remote_type':   j.remote_type,
            'source':        j.source,
            'salary_min':    j.salary_min,
            'salary_max':    j.salary_max,
            'required_skills': j.required_skills or [],
            'url':           j.url,
            'posted_date':   j.posted_date.isoformat() if j.posted_date else None,
        } for j in jobs]
    })


@bp.route('/api/jobs/<int:job_id>', methods=['GET'])
@login_required
def get_job(job_id):
    j = Job.query.get_or_404(job_id)
    return jsonify({
        'id':              j.id,
        'title':           j.title,
        'company':         j.company,
        'location':        j.location,
        'description':     j.description,
        'required_skills': j.required_skills or [],
        'salary_min':      j.salary_min,
        'salary_max':      j.salary_max,
        'job_type':        j.job_type,
        'remote_type':     j.remote_type,
        'source':          j.source,
        'url':             j.url,
        'posted_date':     j.posted_date.isoformat() if j.posted_date else None,
    })


@bp.route('/api/jobs/fetch', methods=['POST'])
@login_required
def fetch_jobs():
    """Trigger live job aggregation from all sources (Adzuna + Remotive + Lever + Greenhouse)."""
    data     = request.get_json() or {}
    query    = data.get('query', 'software developer')
    location = data.get('location', 'remote')
    sources  = data.get('sources')  # optional list: ['remotive', 'lever', 'greenhouse']

    agg  = _get_aggregator()
    jobs = agg.fetch_all(query=query, location=location,
                         max_per_source=25, sources=sources)
    return _store_jobs(jobs)


@bp.route('/api/jobs/fetch/lever', methods=['POST'])
@login_required
def fetch_lever():
    """Fetch jobs from a specific Lever company board."""
    data    = request.get_json() or {}
    company = data.get('company_slug', '').strip()
    query   = data.get('query', '')
    if not company:
        return jsonify({'error': 'company_slug required'}), 400

    jobs = _get_aggregator().fetch_lever(company, query, limit=50)
    return _store_jobs(jobs, provider='Lever', company=company)


@bp.route('/api/jobs/fetch/greenhouse', methods=['POST'])
@login_required
def fetch_greenhouse():
    """Fetch jobs from a specific Greenhouse company board."""
    data    = request.get_json() or {}
    company = data.get('company_slug', '').strip()
    query   = data.get('query', '')
    if not company:
        return jsonify({'error': 'company_slug required'}), 400

    jobs = _get_aggregator().fetch_greenhouse(company, query, limit=50)
    return _store_jobs(jobs, provider='Greenhouse', company=company)


def _store_jobs(jobs, provider='API', company=''):
    """Common helper: persist deduplicated jobs to the DB."""
    added = 0
    for j in jobs:
        ext_id = j.get('external_id')
        if ext_id and Job.query.filter_by(external_id=ext_id).first():
            continue
        job_obj = Job(
            external_id     = ext_id,
            title           = j['title'],
            company         = j['company'],
            location        = j.get('location', ''),
            description     = j.get('description', ''),
            required_skills = j.get('required_skills', []),
            salary_min      = j.get('salary_min', 0),
            salary_max      = j.get('salary_max', 0),
            job_type        = j.get('job_type', 'full-time'),
            remote_type     = j.get('remote_type', 'onsite'),
            source          = j.get('source', provider.lower()),
            url             = j.get('url', ''),
            posted_date     = j.get('posted_date', datetime.utcnow()),
        )
        db.session.add(job_obj)
        added += 1
    db.session.commit()
    total = Job.query.count()
    return jsonify({'success': True, 'fetched': len(jobs), 'new': added, 'total_in_db': total})
