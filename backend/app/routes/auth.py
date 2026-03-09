"""
Auth routes — Login, Register, Logout, and ATS portal connections
"""
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from app import db
from app.models import User, Profile, ATSConnection
from datetime import datetime
from firebase_admin import auth as firebase_auth
import secrets

bp = Blueprint('auth', __name__, url_prefix='/auth')


@bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('jobs.jobs_page'))

    if request.method == 'POST':
        email     = (request.form.get('email') or '').strip().lower()
        password  = request.form.get('password') or ''
        full_name = (request.form.get('full_name') or '').strip()

        if not email or not password or not full_name:
            flash('All fields are required.', 'error')
            return redirect(url_for('auth.register'))

        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'error')
            return redirect(url_for('auth.register'))

        if User.query.filter_by(email=email).first():
            flash('Email already registered. Please log in.', 'error')
            return redirect(url_for('auth.login'))

        user = User(email=email, full_name=full_name)
        user.set_password(password)
        db.session.add(user)
        db.session.flush()   # get user.id before commit

        # Create empty profile
        profile = Profile(user_id=user.id)
        db.session.add(profile)
        db.session.commit()

        login_user(user, remember=True)
        user.touch_login()
        flash('Account created! Welcome aboard.', 'success')
        return redirect(url_for('jobs.jobs_page'))

    return render_template('register.html')


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('jobs.jobs_page'))

    if request.method == 'POST':
        email    = (request.form.get('email') or '').strip().lower()
        password = request.form.get('password') or ''
        remember = bool(request.form.get('remember'))

        user = User.query.filter_by(email=email).first()
        if not user or not user.check_password(password):
            flash('Invalid email or password.', 'error')
            return redirect(url_for('auth.login'))

        if not user.is_active:
            flash('Your account has been deactivated. Contact support.', 'error')
            return redirect(url_for('auth.login'))

        login_user(user, remember=remember)
        user.touch_login()

        next_page = request.args.get('next')
        return redirect(next_page or url_for('jobs.jobs_page'))

    return render_template('login.html')


@bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been signed out.', 'info')
    return redirect(url_for('auth.login'))

@bp.route('/firebase-login', methods=['POST'])
def firebase_login():
    data = request.get_json() or {}
    id_token = data.get('idToken')
    
    if not id_token:
        return jsonify({'error': 'Missing ID token'}), 400
        
    try:
        decoded_token = firebase_auth.verify_id_token(id_token)
        email = decoded_token.get('email')
        name = decoded_token.get('name') or ''
        
        if not email:
            return jsonify({'error': 'Invalid token, no email found'}), 400
            
        user = User.query.filter_by(email=email).first()
        if not user:
            user = User(email=email, full_name=name)
            user.set_password(secrets.token_urlsafe(32))
            db.session.add(user)
            db.session.flush()
            
            profile = Profile(user_id=user.id)
            db.session.add(profile)
            db.session.commit()
            
        login_user(user, remember=True)
        user.touch_login()
        
        return jsonify({'success': True, 'redirect': url_for('jobs.jobs_page')})
        
    except Exception as e:
        print(f"Firebase token verification failed: {e}")
        return jsonify({'error': 'Unauthorized', 'message': str(e)}), 401


# ─────────────────────────────────────────
# ATS Portal Connections (Lever / Greenhouse)
# ─────────────────────────────────────────

@bp.route('/ats/connect', methods=['POST'])
@login_required
def connect_ats():
    """Connect a Lever or Greenhouse company board to the user's account."""
    data         = request.get_json() or {}
    provider     = (data.get('provider') or '').lower().strip()
    company_slug = (data.get('company_slug') or '').lower().strip().replace(' ', '-')
    company_name = data.get('company_name') or company_slug.replace('-', ' ').title()

    if provider not in ('lever', 'greenhouse'):
        return jsonify({'error': 'provider must be lever or greenhouse'}), 400
    if not company_slug:
        return jsonify({'error': 'company_slug is required'}), 400

    existing = ATSConnection.query.filter_by(
        user_id=current_user.id,
        provider=provider,
        company_slug=company_slug
    ).first()

    if existing:
        return jsonify({'message': 'Already connected', 'id': existing.id})

    conn = ATSConnection(
        user_id     = current_user.id,
        provider    = provider,
        company_slug= company_slug,
        company_name= company_name,
    )
    db.session.add(conn)
    db.session.commit()
    return jsonify({'success': True, 'id': conn.id,
                    'message': f'Connected to {company_name} ({provider})'})


@bp.route('/ats/connections', methods=['GET'])
@login_required
def list_ats_connections():
    """List all ATS connections for the current user."""
    conns = ATSConnection.query.filter_by(user_id=current_user.id).all()
    return jsonify([{
        'id':           c.id,
        'provider':     c.provider,
        'company_slug': c.company_slug,
        'company_name': c.company_name,
        'connected_at': c.connected_at.isoformat(),
        'last_synced':  c.last_synced.isoformat() if c.last_synced else None,
        'job_count':    c.job_count,
    } for c in conns])


@bp.route('/ats/connections/<int:conn_id>', methods=['DELETE'])
@login_required
def delete_ats_connection(conn_id):
    """Remove an ATS connection."""
    conn = ATSConnection.query.filter_by(id=conn_id, user_id=current_user.id).first_or_404()
    db.session.delete(conn)
    db.session.commit()
    return jsonify({'success': True})


@bp.route('/ats/sync/<int:conn_id>', methods=['POST'])
@login_required
def sync_ats_connection(conn_id):
    """Sync jobs from a specific ATS connection."""
    conn = ATSConnection.query.filter_by(id=conn_id, user_id=current_user.id).first_or_404()
    from app.services.job_aggregator import JobAggregator
    from app.models import Job
    from flask import current_app

    agg  = JobAggregator(
        adzuna_app_id =current_app.config.get('ADZUNA_APP_ID',  ''),
        adzuna_app_key=current_app.config.get('ADZUNA_APP_KEY', ''),
    )

    if conn.provider == 'lever':
        raw_jobs = agg.fetch_lever(conn.company_slug)
    elif conn.provider == 'greenhouse':
        raw_jobs = agg.fetch_greenhouse(conn.company_slug)
    else:
        return jsonify({'error': 'Unknown provider'}), 400

    added = 0
    for j in raw_jobs:
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
            source          = conn.provider,
            url             = j.get('url', ''),
            posted_date     = j.get('posted_date', datetime.utcnow()),
        )
        db.session.add(job_obj)
        added += 1

    conn.last_synced = datetime.utcnow()
    conn.job_count   = (conn.job_count or 0) + added
    db.session.commit()

    return jsonify({
        'success':  True,
        'fetched':  len(raw_jobs),
        'new':      added,
        'provider': conn.provider,
        'company':  conn.company_name,
    })
