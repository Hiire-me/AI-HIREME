import os
from pathlib import Path

# Base directory of the project (one level above backend/)
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Detect cloud / container environment (Hugging Face Spaces, Render, etc.)
IS_VERCEL = bool(os.environ.get('VERCEL'))
IS_CLOUD  = bool(os.environ.get('DATABASE_URL'))  # any external DB = cloud mode


def _fix_db_url(url: str) -> str:
    """SQLAlchemy v2 requires 'postgresql://' not 'postgres://'.
    Supabase and many other providers return the old form — fix it here."""
    if url and url.startswith('postgres://'):
        url = 'postgresql://' + url[len('postgres://'):]
    return url


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'

    # Database
    # Priority: DATABASE_URL env var (Supabase/Neon/etc.) → local SQLite
    if IS_VERCEL:
        _db_path = '/tmp/jobagent.db'
    else:
        _db_path = os.path.join(BASE_DIR, 'backend', 'instance', 'jobagent.db')

    _raw_db_url = os.environ.get('DATABASE_URL') or f'sqlite:///{_db_path}'
    SQLALCHEMY_DATABASE_URI = _fix_db_url(_raw_db_url)
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Required for Supabase/PgBouncer connection pooling
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
    }

    # Upload folder for resumes
    # In cloud/Docker environments (no permanent storage) use /tmp
    if IS_VERCEL or IS_CLOUD:
        UPLOAD_FOLDER = '/tmp/uploads'
    else:
        UPLOAD_FOLDER = os.path.join(BASE_DIR, 'data', 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB max upload

    # Skills database path
    SKILLS_DB_PATH = os.path.join(BASE_DIR, 'data', 'skills_database.json')

    # AI Keys (optional — app works without them)
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
    ADZUNA_APP_ID  = os.environ.get('ADZUNA_APP_ID', '')
    ADZUNA_APP_KEY = os.environ.get('ADZUNA_APP_KEY', '')
    RESEND_API_KEY = os.environ.get('RESEND_API_KEY', '')

    # Redis and Celery
    REDIS_URL = os.environ.get('REDIS_URL') or 'redis://localhost:6379/0'
    CELERY_BROKER_URL = REDIS_URL
    CELERY_RESULT_BACKEND = REDIS_URL

    # Run Celery tasks synchronously when Redis is not available (cloud free tier)
    # Set REDIS_URL env variable to disable this and use a real Celery worker.
    CELERY_TASK_ALWAYS_EAGER = not bool(os.environ.get('REDIS_URL'))
    CELERY_TASK_EAGER_PROPAGATES = True

