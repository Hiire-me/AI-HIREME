from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from app import db
from app.models import Profile

bp = Blueprint('profile', __name__)


@bp.route('/api/profile', methods=['GET'])
@login_required
def get_profile():
    p = current_user.profile
    return jsonify({
        'full_name':          current_user.full_name,
        'email':              current_user.email,
        'phone':              current_user.phone,
        'summary':            p.summary            if p else '',
        'skills':             p.skills             if p else [],
        'experience':         p.experience         if p else [],
        'education':          p.education          if p else [],
        'desired_titles':     p.desired_titles     if p else [],
        'desired_locations':  p.desired_locations  if p else [],
        'remote_preference':  p.remote_preference  if p else 'hybrid',
        'min_salary':         p.min_salary         if p else 0,
        'max_salary':         p.max_salary         if p else 0,
        'auto_apply_enabled': p.auto_apply_enabled if p else False,
        'applications_per_day': p.applications_per_day if p else 5,
    })


@bp.route('/api/profile', methods=['POST', 'PUT'])
@login_required
def update_profile():
    data = request.get_json() or {}

    # Update user table fields
    if 'full_name' in data:
        current_user.full_name = data['full_name']
    if 'phone' in data:
        current_user.phone = data['phone']

    # Update or create profile
    p = current_user.profile
    if not p:
        p = Profile(user_id=current_user.id)
        db.session.add(p)

    str_fields = ['summary', 'remote_preference']
    json_fields= ['skills', 'experience', 'education',
                  'desired_titles', 'desired_locations']
    int_fields = ['min_salary', 'max_salary', 'applications_per_day']
    bool_fields= ['auto_apply_enabled']

    for f in str_fields:
        if f in data:
            setattr(p, f, data[f])
    for f in json_fields:
        if f in data:
            setattr(p, f, data[f])
    for f in int_fields:
        if f in data:
            setattr(p, f, int(data[f]))
    for f in bool_fields:
        if f in data:
            setattr(p, f, bool(data[f]))

    db.session.commit()
    return jsonify({'success': True})
