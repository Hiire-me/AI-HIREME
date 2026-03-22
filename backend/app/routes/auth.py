from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_user, logout_user, current_user, login_required
from datetime import datetime
from app import db
from app.models import User, Profile, ATSConnection

bp = Blueprint('auth', __name__, url_prefix='/auth')

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.dashboard_page'))

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        remember = True if request.form.get('remember') else False

        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            login_user(user, remember=remember)
            user.touch_login()
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('dashboard.dashboard_page'))
        else:
            flash('Login unsuccessful. Please check your email and password.', 'error')

    return render_template('login.html', is_auth_page=True)

@bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.dashboard_page'))

    if request.method == 'POST':
        full_name = request.form.get('full_name')
        email = request.form.get('email')
        password = request.form.get('password')

        user = User.query.filter_by(email=email).first()
        if user:
            flash('Email address already exists. Please log in.', 'error')
            return redirect(url_for('auth.login'))

        new_user = User(full_name=full_name, email=email)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.flush()

        # Create basic profile
        profile = Profile(user_id=new_user.id, summary='')
        db.session.add(profile)
        db.session.commit()

        login_user(new_user)
        return redirect(url_for('dashboard.dashboard_page'))

    return render_template('register.html', is_auth_page=True)

@bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('jobs.jobs_page'))


# ─────────────────────────────────────────
# ATS Portal Connections
# ─────────────────────────────────────────

@bp.route('/ats/connections', methods=['GET'])
@login_required
def list_ats_connections():
    conns = ATSConnection.query.filter_by(user_id=current_user.id).all()
    return jsonify([{
        'id':           c.id,
        'provider':     c.provider,
        'company_slug': c.company_slug,
        'company_name': c.company_name or c.company_slug,
        'connected_at': c.connected_at.isoformat() if c.connected_at else None,
        'last_synced':  c.last_synced.isoformat() if c.last_synced else None,
        'job_count':    c.job_count or 0,
    } for c in conns])


@bp.route('/ats/connect', methods=['POST'])
@login_required
def connect_ats():
    data = request.get_json() or {}
    provider = data.get('provider', '').lower()
    slug = data.get('company_slug', '').strip().lower()
    name = data.get('company_name', '').strip() or slug.title()

    if provider not in ('lever', 'greenhouse'):
        return jsonify({'error': 'Provider must be lever or greenhouse'}), 400
    if not slug:
        return jsonify({'error': 'company_slug required'}), 400

    existing = ATSConnection.query.filter_by(
        user_id=current_user.id, provider=provider, company_slug=slug
    ).first()
    if existing:
        return jsonify({'error': 'Portal already saved'}), 400

    conn = ATSConnection(
        user_id=current_user.id,
        provider=provider,
        company_slug=slug,
        company_name=name,
    )
    db.session.add(conn)
    db.session.commit()
    return jsonify({'success': True, 'id': conn.id})


@bp.route('/ats/sync/<int:conn_id>', methods=['POST'])
@login_required
def sync_ats(conn_id):
    conn = ATSConnection.query.filter_by(id=conn_id, user_id=current_user.id).first_or_404()

    from flask import current_app
    from app.services.job_aggregator import JobAggregator
    from app.models import Job

    agg = JobAggregator(
        adzuna_app_id=current_app.config.get('ADZUNA_APP_ID', ''),
        adzuna_app_key=current_app.config.get('ADZUNA_APP_KEY', ''),
    )

    if conn.provider == 'lever':
        jobs = agg.fetch_lever(conn.company_slug, '', limit=50)
    else:
        jobs = agg.fetch_greenhouse(conn.company_slug, '', limit=50)

    added = 0
    for j in jobs:
        ext_id = j.get('external_id')
        if ext_id and Job.query.filter_by(external_id=ext_id).first():
            continue
        job_obj = Job(
            external_id=ext_id, title=j['title'], company=j['company'],
            location=j.get('location', ''), description=j.get('description', ''),
            required_skills=j.get('required_skills', []),
            salary_min=j.get('salary_min', 0), salary_max=j.get('salary_max', 0),
            job_type=j.get('job_type', 'full-time'), remote_type=j.get('remote_type', 'onsite'),
            source=conn.provider, url=j.get('url', ''),
            posted_date=j.get('posted_date', datetime.utcnow()),
        )
        db.session.add(job_obj)
        added += 1

    conn.last_synced = datetime.utcnow()
    conn.job_count = (conn.job_count or 0) + added
    db.session.commit()

    return jsonify({'success': True, 'fetched': len(jobs), 'new': added})


@bp.route('/ats/connections/<int:conn_id>', methods=['DELETE'])
@login_required
def delete_ats_connection(conn_id):
    conn = ATSConnection.query.filter_by(id=conn_id, user_id=current_user.id).first_or_404()
    db.session.delete(conn)
    db.session.commit()
    return jsonify({'success': True})
