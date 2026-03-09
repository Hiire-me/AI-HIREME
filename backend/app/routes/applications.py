from flask import Blueprint, jsonify, request, render_template
from flask_login import login_required, current_user
from sqlalchemy import desc
from datetime import datetime
from app import db
from app.models import Application, Job

bp = Blueprint('applications', __name__)


@bp.route('/applications')
@login_required
def applications_page():
    return render_template('applications.html')


@bp.route('/api/applications', methods=['GET'])
@login_required
def get_applications():
    status = request.args.get('status', '')
    limit  = request.args.get('limit', 100, type=int)

    q = Application.query.filter_by(user_id=current_user.id).join(Job)
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
@login_required
def create_application():
    data   = request.get_json() or {}
    job_id = data.get('job_id')
    if not job_id:
        return jsonify({'error': 'job_id required'}), 400

    if not Job.query.get(job_id):
        return jsonify({'error': 'Job not found'}), 404

    if Application.query.filter_by(user_id=current_user.id, job_id=job_id).first():
        return jsonify({'error': 'Already applied to this job'}), 400

    app_obj = Application(
        user_id     = current_user.id,
        job_id      = job_id,
        match_score = data.get('match_score', 0),
        status      = 'submitted',
        cover_letter= data.get('cover_letter', ''),
    )
    db.session.add(app_obj)
    db.session.commit()
    return jsonify({'success': True, 'id': app_obj.id})


@bp.route('/api/applications/<int:app_id>', methods=['PATCH'])
@login_required
def update_application(app_id):
    app_obj = Application.query.filter_by(id=app_id, user_id=current_user.id).first_or_404()
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
@login_required
def delete_application(app_id):
    app_obj = Application.query.filter_by(id=app_id, user_id=current_user.id).first_or_404()
    db.session.delete(app_obj)
    db.session.commit()
    return jsonify({'success': True})

@bp.route('/api/applications/<int:app_id>/auto-apply', methods=['POST'])
@login_required
def trigger_auto_apply(app_id):
    from app.tasks import execute_auto_apply
    app_obj = Application.query.filter_by(id=app_id, user_id=current_user.id).first_or_404()
    
    # Don't re-apply if already reviewing, interview, offer, or auto-applied
    if app_obj.auto_applied or app_obj.status in ('reviewing', 'interview', 'offer'):
        return jsonify({'error': 'Application already in progress or completed'}), 400

    execute_auto_apply.delay(app_obj.id)
    return jsonify({'success': True, 'message': 'Auto-apply task queued'})


@bp.route('/api/applications/stats', methods=['GET'])
@login_required
def get_stats():
    uid   = current_user.id
    total = Application.query.filter_by(user_id=uid).count()
    def cnt(s): return Application.query.filter_by(user_id=uid, status=s).count()

    return jsonify({
        'total':       total,
        'submitted':   cnt('submitted'),
        'reviewing':   cnt('reviewing'),
        'interview':   cnt('interview'),
        'offer':       cnt('offer'),
        'rejected':    cnt('rejected'),
    })
