from flask import Blueprint, jsonify, request, render_template
from flask_login import login_required
from sqlalchemy import desc
from datetime import datetime
from app import db
from app.models import User, Application, Job, JobMatch, Resume
from app.services.email_service import EmailService

bp = Blueprint('applications', __name__)


@bp.route('/applications')
def applications_page():
    return render_template('applications.html')


@bp.route('/api/applications', methods=['GET'])
def get_applications():
    status = request.args.get('status', '')
    limit  = request.args.get('limit', 100, type=int)

    q = Application.query.filter_by(user_id=1).join(Job)
    if status and status != 'all':
        q = q.filter(Application.status == status)
    apps = q.order_by(desc(Application.applied_at)).limit(limit).all()

    return jsonify([{
        'id':          a.id,
        'status':      a.status,
        'match_score': a.match_score,
        'applied_at':  a.applied_at.isoformat(),
        'status_updated': a.status_updated.isoformat(),
        'job': {
            'id':       a.job.id,
            'title':    a.job.title,
            'company':  a.job.company,
            'location': a.job.location,
            'url':      a.job.url,
        }
    } for a in apps])


@bp.route('/api/applications', methods=['POST'])
def create_application():
    data   = request.get_json() or {}
    job_id = data.get('job_id')
    if not job_id:
        return jsonify({'error': 'job_id required'}), 400

    if not Job.query.get(job_id):
        return jsonify({'error': 'Job not found'}), 404

    if Application.query.filter_by(user_id=1, job_id=job_id).first():
        return jsonify({'error': 'Already applied to this job'}), 400

    app_obj = Application(
        user_id     = 1,
        job_id      = job_id,
        match_score = data.get('match_score', 0),
        status      = 'submitted',
        cover_letter= data.get('cover_letter', ''),
    )
    db.session.add(app_obj)
    db.session.commit()

    # Send email notification
    try:
        user = User.query.get(1)
        EmailService.send_application_notification(
            user.email,
            {
                'title': app_obj.job.title,
                'company': app_obj.job.company,
                'location': app_obj.job.location,
                'url': app_obj.job.url
            }
        )
    except Exception as e:
        print(f"[create_application] Warning: Could not send notification email: {e}")

    return jsonify({'success': True, 'id': app_obj.id})


@bp.route('/api/applications/<int:app_id>', methods=['PATCH'])
def update_application(app_id):
    app_obj = Application.query.filter_by(id=app_id, user_id=1).first_or_404()
    data    = request.get_json() or {}

    valid_statuses = {'submitted', 'reviewing', 'interview', 'offer', 'rejected'}
    if 'status' in data and data['status'] in valid_statuses:
        app_obj.status         = data['status']
        app_obj.status_updated = datetime.utcnow()

    if 'cover_letter' in data:
        app_obj.cover_letter = data['cover_letter']

    db.session.commit()
    return jsonify({'success': True})


@bp.route('/api/applications/<int:app_id>', methods=['DELETE'])
def delete_application(app_id):
    app_obj = Application.query.filter_by(id=app_id, user_id=1).first_or_404()
    db.session.delete(app_obj)
    db.session.commit()
    return jsonify({'success': True})

@bp.route('/api/applications/<int:app_id>/auto-apply', methods=['POST'])
def trigger_auto_apply(app_id):
    from app.tasks import execute_auto_apply
    app_obj = Application.query.filter_by(id=app_id, user_id=1).first_or_404()

    # Don't re-apply if already reviewing, interview, offer, or auto-applied
    if app_obj.auto_applied or app_obj.status in ('reviewing', 'interview', 'offer'):
        return jsonify({'error': 'Application already in progress or completed'}), 400

    execute_auto_apply.delay(app_obj.id)
    return jsonify({'success': True, 'message': 'Auto-apply task queued'})


@bp.route('/api/auto-apply/run', methods=['POST'])
def run_auto_apply_loop():
    """
    Manually trigger the automated matching + auto-apply loop.
    Reads the profile threshold, finds high-scoring matches, and queues the bot.
    """
    from app.tasks import auto_apply_loop
    try:
        result = auto_apply_loop()
        return jsonify({'success': True, 'result': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/api/applications/stats', methods=['GET'])
def get_stats():
    uid   = 1
    total = Application.query.filter_by(user_id=1).count()
    def cnt(s): return Application.query.filter_by(user_id=1, status=s).count()

    return jsonify({
        'total':       total,
        'submitted':   cnt('submitted'),
        'reviewing':   cnt('reviewing'),
        'interview':   cnt('interview'),
        'offer':       cnt('offer'),
        'rejected':    cnt('rejected'),
    })


@bp.route('/api/applications/suggested', methods=['GET'])
def get_suggested_applications():
    """Return jobs with match_score >= 35% that the user hasn't applied to yet."""
    min_score = request.args.get('min_score', 35, type=float)

    # Get all resume IDs for the user
    resumes = Resume.query.filter_by(user_id=1).all()
    resume_ids = [r.id for r in resumes]
    if not resume_ids:
        return jsonify([])

    # Get all job IDs the user already applied to
    applied_job_ids = [a.job_id for a in Application.query.filter_by(user_id=1).all()]

    # Query matches above threshold, excluding already-applied jobs
    query = (JobMatch.query
             .filter(JobMatch.resume_id.in_(resume_ids))
             .filter(JobMatch.match_score >= min_score)
             .order_by(desc(JobMatch.match_score)))

    if applied_job_ids:
        query = query.filter(~JobMatch.job_id.in_(applied_job_ids))

    matches = query.limit(20).all()

    result = []
    for m in matches:
        job = m.job
        if not job:
            continue
        result.append({
            'match_id':       m.id,
            'job_id':         job.id,
            'match_score':    round(m.match_score, 1),
            'matched_skills': m.matched_skills or [],
            'missing_skills': m.missing_skills or [],
            'recommendation': m.recommendation,
            'job': {
                'id':       job.id,
                'title':    job.title,
                'company':  job.company,
                'location': job.location,
                'url':      job.url,
            }
        })

    return jsonify(result)
