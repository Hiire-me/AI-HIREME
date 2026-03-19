import os
from pathlib import Path

# Base directory of the project (one level above backend/)
BASE_DIR = Path(__file__).resolve().parent.parent.parent

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'

    # SQLite default — stored in backend/instance/
    _db_path = os.path.join(BASE_DIR, 'backend', 'instance', 'jobagent.db')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or f'sqlite:///{_db_path}'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Upload folder for resumes
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'data', 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB max upload

    # Skills database path
    SKILLS_DB_PATH = os.path.join(BASE_DIR, 'data', 'skills_database.json')

    # AI Keys (optional — app works without them)
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
    ADZUNA_APP_ID  = os.environ.get('ADZUNA_APP_ID', '')
    ADZUNA_APP_KEY = os.environ.get('ADZUNA_APP_KEY', '')
    RESEND_API_KEY = os.environ.get('RESEND_API_KEY', 're_24KanH1p_FFy9c4gbkNKwhAYypqtwc3gj')

    # Redis and Celery
    REDIS_URL = os.environ.get('REDIS_URL') or 'redis://localhost:6379/0'
    CELERY_BROKER_URL = REDIS_URL
    CELERY_RESULT_BACKEND = REDIS_URL

    # Run Celery tasks synchronously when Redis is not available (local/Windows dev)
    # Set REDIS_URL env variable to disable this and use a real Celery worker.
    CELERY_TASK_ALWAYS_EAGER = not bool(os.environ.get('REDIS_URL'))
    CELERY_TASK_EAGER_PROPAGATES = True
