from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, current_user, login_required
from app import db
from app.models import User, Profile

bp = Blueprint('auth', __name__, url_prefix='/auth')

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('jobs.jobs_page'))

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        remember = True if request.form.get('remember') else False

        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            login_user(user, remember=remember)
            user.touch_login()
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('jobs.jobs_page'))
        else:
            flash('Login unsuccessful. Please check your email and password.', 'error')

    return render_template('login.html', is_auth_page=True)

@bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('jobs.jobs_page'))

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
        return redirect(url_for('jobs.jobs_page'))

    return render_template('register.html', is_auth_page=True)

@bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('jobs.jobs_page'))
