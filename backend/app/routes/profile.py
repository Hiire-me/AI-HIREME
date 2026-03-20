from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from app import db
from app.models import User, Profile

bp = Blueprint('profile', __name__)


@bp.route('/api/profile', methods=['GET'])
@login_required
def get_profile():
    user = current_user
    p = user.profile
    return jsonify({
        'full_name':          user.full_name,
        'email':              user.email,
        'phone':              user.phone,
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
        'auto_apply_match_threshold': p.auto_apply_match_threshold if p else 85,
        # Rules Engine
        'company_blacklist':  p.company_blacklist  if p else [],
        'company_whitelist':  p.company_whitelist  if p else [],
        'keyword_blockers':   p.keyword_blockers   if p else [],
        'stealth_mode':       p.stealth_mode       if p else False,
        'resume_extra':       p.resume_extra       if p else {},
    })


@bp.route('/api/profile', methods=['POST', 'PUT'])
@login_required
def update_profile():
    data = request.get_json() or {}
    user = current_user

    # Update user table fields
    if 'full_name' in data:
        user.full_name = data['full_name']
    if 'phone' in data:
        user.phone = data['phone']

    # Update or create profile
    p = user.profile
    if not p:
        p = Profile(user_id=current_user.id)
        db.session.add(p)

    str_fields  = ['summary', 'remote_preference']
    json_fields = ['skills', 'experience', 'education',
                   'desired_titles', 'desired_locations', 'resume_extra',
                   'company_blacklist', 'company_whitelist', 'keyword_blockers']
    int_fields  = ['min_salary', 'max_salary', 'applications_per_day',
                   'auto_apply_match_threshold']
    bool_fields = ['auto_apply_enabled', 'stealth_mode']

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
