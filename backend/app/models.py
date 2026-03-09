from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db, login_manager
import secrets


# ─────────────────────────────────────────
# User & Auth
# ─────────────────────────────────────────

class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id            = db.Column(db.Integer, primary_key=True)
    email         = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name     = db.Column(db.String(100))
    phone         = db.Column(db.String(30))
    is_active     = db.Column(db.Boolean, default=True)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    last_login    = db.Column(db.DateTime)

    # Relationships
    profile      = db.relationship('Profile', backref='user', uselist=False,
                                   cascade='all, delete-orphan')
    resumes      = db.relationship('Resume', backref='user', cascade='all, delete-orphan')
    applications = db.relationship('Application', backref='user', cascade='all, delete-orphan')
    ats_connections = db.relationship('ATSConnection', backref='user', cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def touch_login(self):
        self.last_login = datetime.utcnow()
        db.session.commit()

    def get_ats_connection(self, provider: str):
        """Get the ATS connection for a given provider (lever / greenhouse)."""
        return ATSConnection.query.filter_by(user_id=self.id, provider=provider).first()


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ─────────────────────────────────────────
# ATS Connections (Lever / Greenhouse)
# ─────────────────────────────────────────

class ATSConnection(db.Model):
    """
    Tracks which ATS portals a user has connected.
    Lever and Greenhouse public job boards don't require auth —
    but users can pin specific company slugs to always fetch from.
    """
    __tablename__ = 'ats_connections'

    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    provider    = db.Column(db.String(30), nullable=False)  # 'lever' | 'greenhouse'
    company_slug= db.Column(db.String(100), nullable=False) # e.g. 'stripe', 'shopify'
    company_name= db.Column(db.String(200))                 # Display name
    connected_at= db.Column(db.DateTime, default=datetime.utcnow)
    last_synced = db.Column(db.DateTime)
    job_count   = db.Column(db.Integer, default=0)          # Jobs fetched from this portal

    __table_args__ = (db.UniqueConstraint('user_id', 'provider', 'company_slug',
                                          name='uq_user_ats_company'),)


# ─────────────────────────────────────────
# User Profile & Preferences
# ─────────────────────────────────────────

class Profile(db.Model):
    __tablename__ = 'profiles'

    id      = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    summary   = db.Column(db.Text)
    skills    = db.Column(db.JSON, default=list)   # ['Python', 'SQL', …]
    experience= db.Column(db.JSON, default=list)   # [{title, company, start, end, desc}]
    education = db.Column(db.JSON, default=list)   # [{degree, field, school, year}]

    # Job preferences
    desired_titles    = db.Column(db.JSON, default=list)
    desired_locations = db.Column(db.JSON, default=list)
    remote_preference = db.Column(db.String(20), default='hybrid')  # remote|hybrid|onsite
    min_salary        = db.Column(db.Integer, default=0)
    max_salary        = db.Column(db.Integer, default=0)

    # Auto-apply settings
    auto_apply_enabled   = db.Column(db.Boolean, default=False)
    applications_per_day = db.Column(db.Integer, default=5)

    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ─────────────────────────────────────────
# Resume
# ─────────────────────────────────────────

class Resume(db.Model):
    __tablename__ = 'resumes'

    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    filename    = db.Column(db.String(255))
    file_path   = db.Column(db.String(500))
    raw_text    = db.Column(db.Text)

    # Extracted data
    extracted_skills  = db.Column(db.JSON, default=list)
    personal_info     = db.Column(db.JSON, default=dict)  # {name, email, phone, location}
    parsed_experience = db.Column(db.JSON, default=list)
    parsed_education  = db.Column(db.JSON, default=list)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    matches    = db.relationship('JobMatch', backref='resume', cascade='all, delete-orphan')


# ─────────────────────────────────────────
# Jobs
# ─────────────────────────────────────────

class Job(db.Model):
    __tablename__ = 'jobs'

    id          = db.Column(db.Integer, primary_key=True)
    external_id = db.Column(db.String(100), unique=True, nullable=True)

    title       = db.Column(db.String(200), nullable=False)
    company     = db.Column(db.String(200), nullable=False)
    location    = db.Column(db.String(200))
    description = db.Column(db.Text)
    required_skills = db.Column(db.JSON, default=list)  # ['Python', 'SQL', …]
    salary_min  = db.Column(db.Integer)
    salary_max  = db.Column(db.Integer)
    job_type    = db.Column(db.String(50))    # full-time | part-time | contract
    remote_type = db.Column(db.String(20))   # remote | hybrid | onsite

    source      = db.Column(db.String(50))   # adzuna | remotive | seed
    url         = db.Column(db.String(500))
    posted_date = db.Column(db.DateTime)
    scraped_at  = db.Column(db.DateTime, default=datetime.utcnow)

    matches      = db.relationship('JobMatch', backref='job', cascade='all, delete-orphan')
    applications = db.relationship('Application', backref='job', cascade='all, delete-orphan')


# ─────────────────────────────────────────
# Skill Matching
# ─────────────────────────────────────────

class JobMatch(db.Model):
    __tablename__ = 'job_matches'

    id        = db.Column(db.Integer, primary_key=True)
    resume_id = db.Column(db.Integer, db.ForeignKey('resumes.id'), nullable=False)
    job_id    = db.Column(db.Integer, db.ForeignKey('jobs.id'), nullable=False)

    match_score     = db.Column(db.Float, default=0.0)   # 0–100
    matched_skills  = db.Column(db.JSON, default=list)
    missing_skills  = db.Column(db.JSON, default=list)
    recommendation  = db.Column(db.String(50))            # Strong Match | Good Match | Consider

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('resume_id', 'job_id', name='uq_resume_job'),)


# ─────────────────────────────────────────
# Applications
# ─────────────────────────────────────────

class Application(db.Model):
    __tablename__ = 'applications'

    id      = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    job_id  = db.Column(db.Integer, db.ForeignKey('jobs.id'), nullable=False)

    match_score  = db.Column(db.Float, default=0.0)
    status       = db.Column(db.String(50), default='submitted')
    # submitted → reviewing → interview → offer | rejected

    cover_letter    = db.Column(db.Text)
    tailored_resume = db.Column(db.Text)
    auto_applied    = db.Column(db.Boolean, default=False)

    applied_at      = db.Column(db.DateTime, default=datetime.utcnow)
    status_updated  = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('user_id', 'job_id', name='uq_user_job'),)
