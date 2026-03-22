from flask import Blueprint, jsonify, render_template
from flask_login import login_required, current_user
from sqlalchemy import func
from datetime import datetime, timedelta
from app import db
from app.models import Application, JobMatch, Resume, Job


bp = Blueprint('analytics', __name__)


@bp.route('/analytics')
@login_required
def analytics_page():
    return render_template('analytics.html')


@bp.route('/api/analytics/overview', methods=['GET'])
@login_required
def analytics_overview():
    """Return overall analytics for the current user."""
    user_id = current_user.id

    # Application stats
    total_apps = Application.query.filter_by(user_id=user_id).count()
    submitted = Application.query.filter_by(user_id=user_id, status='submitted').count()
    reviewing = Application.query.filter_by(user_id=user_id, status='reviewing').count()
    interviews = Application.query.filter_by(user_id=user_id, status='interview').count()
    offers = Application.query.filter_by(user_id=user_id, status='offer').count()
    rejected = Application.query.filter_by(user_id=user_id, status='rejected').count()

    # Match stats
    resume_ids = [r.id for r in Resume.query.filter_by(user_id=user_id).all()]
    total_matches = 0
    avg_match_score = 0
    strong_matches = 0
    good_matches = 0

    if resume_ids:
        total_matches = JobMatch.query.filter(JobMatch.resume_id.in_(resume_ids)).count()
        avg_result = db.session.query(func.avg(JobMatch.match_score)).filter(
            JobMatch.resume_id.in_(resume_ids)
        ).scalar()
        avg_match_score = round(avg_result or 0, 1)
        strong_matches = JobMatch.query.filter(
            JobMatch.resume_id.in_(resume_ids),
            JobMatch.match_score >= 70
        ).count()
        good_matches = JobMatch.query.filter(
            JobMatch.resume_id.in_(resume_ids),
            JobMatch.match_score >= 45,
            JobMatch.match_score < 70
        ).count()

    # Response rate (interview + offer) / total
    response_rate = 0
    if total_apps > 0:
        response_rate = round(((interviews + offers) / total_apps) * 100, 1)

    # Top matched skills across all matches
    top_skills = {}
    if resume_ids:
        matches = JobMatch.query.filter(JobMatch.resume_id.in_(resume_ids)).all()
        for m in matches:
            for skill in (m.matched_skills or []):
                top_skills[skill] = top_skills.get(skill, 0) + 1

    skill_ranking = sorted(top_skills.items(), key=lambda x: x[1], reverse=True)[:10]

    return jsonify({
        'applications': {
            'total': total_apps,
            'submitted': submitted,
            'reviewing': reviewing,
            'interview': interviews,
            'offer': offers,
            'rejected': rejected,
        },
        'matches': {
            'total': total_matches,
            'avg_score': avg_match_score,
            'strong': strong_matches,
            'good': good_matches,
        },
        'response_rate': response_rate,
        'top_skills': [{'name': s[0], 'count': s[1]} for s in skill_ranking],
    })


@bp.route('/api/analytics/timeline', methods=['GET'])
@login_required
def analytics_timeline():
    """Return application activity grouped by day for the last 30 days."""
    user_id = current_user.id
    since = datetime.utcnow() - timedelta(days=30)

    apps = Application.query.filter(
        Application.user_id == user_id,
        Application.applied_at >= since
    ).all()

    # Group by date
    by_day = {}
    for a in apps:
        day = a.applied_at.strftime('%Y-%m-%d')
        by_day[day] = by_day.get(day, 0) + 1

    # Fill in empty days
    timeline = []
    for i in range(30):
        d = (datetime.utcnow() - timedelta(days=29 - i)).strftime('%Y-%m-%d')
        timeline.append({'date': d, 'count': by_day.get(d, 0)})

    return jsonify(timeline)
