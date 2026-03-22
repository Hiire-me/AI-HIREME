from flask import Blueprint, render_template, jsonify
from flask_login import login_required, current_user
from sqlalchemy import desc
from app import db
from app.models import Application, Job, JobMatch, Resume


bp = Blueprint('dashboard', __name__)


@bp.route('/dashboard')
@login_required
def dashboard_page():
    return render_template('dashboard.html')


@bp.route('/api/dashboard/summary', methods=['GET'])
@login_required
def dashboard_summary():
    """Quick summary for the dashboard overview cards."""
    user_id = current_user.id

    total_apps = Application.query.filter_by(user_id=user_id).count()
    interviews = Application.query.filter_by(user_id=user_id, status='interview').count()
    offers = Application.query.filter_by(user_id=user_id, status='offer').count()
    total_jobs = Job.query.count()

    # Match stats
    resume_ids = [r.id for r in Resume.query.filter_by(user_id=user_id).all()]
    total_matches = 0
    if resume_ids:
        total_matches = JobMatch.query.filter(JobMatch.resume_id.in_(resume_ids)).count()

    # Recent applications
    recent_apps = Application.query.filter_by(user_id=user_id) \
        .join(Job).order_by(desc(Application.applied_at)).limit(5).all()

    recent_list = [{
        'id': a.id,
        'status': a.status,
        'match_score': a.match_score,
        'applied_at': a.applied_at.isoformat(),
        'job': {
            'title': a.job.title,
            'company': a.job.company,
        }
    } for a in recent_apps]

    # Recent top matches
    top_matches = []
    if resume_ids:
        matches = JobMatch.query.filter(
            JobMatch.resume_id.in_(resume_ids)
        ).order_by(desc(JobMatch.match_score)).limit(5).all()
        top_matches = [{
            'score': round(m.match_score, 1),
            'recommendation': m.recommendation,
            'job': {
                'id': m.job.id,
                'title': m.job.title,
                'company': m.job.company,
            }
        } for m in matches if m.job]

    # Latest jobs in DB
    latest_jobs = Job.query.order_by(desc(Job.posted_date)).limit(8).all()
    job_feed = [{
        'id': j.id,
        'title': j.title,
        'company': j.company,
        'source': j.source,
        'posted_date': j.posted_date.isoformat() if j.posted_date else None,
    } for j in latest_jobs]

    return jsonify({
        'stats': {
            'total_applications': total_apps,
            'interviews': interviews,
            'offers': offers,
            'total_jobs': total_jobs,
            'total_matches': total_matches,
        },
        'recent_applications': recent_list,
        'top_matches': top_matches,
        'job_feed': job_feed,
    })
