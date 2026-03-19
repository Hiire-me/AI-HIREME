from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_cors import CORS
import os
from dotenv import load_dotenv

load_dotenv()

db = SQLAlchemy()
migrate = Migrate()

# Flask-SocketIO instance — initialized lazily in create_app()
try:
    from flask_socketio import SocketIO
    socketio = SocketIO()
    HAS_SOCKETIO = True
except ImportError:
    socketio = None
    HAS_SOCKETIO = False

def create_app():
    from app.config import Config

    # Template/static folders live in ../../frontend relative to this file
    base = os.path.dirname(os.path.abspath(__file__))
    tmpl = os.path.join(base, '..', '..', 'frontend', 'templates')
    stat = os.path.join(base, '..', '..', 'frontend', 'static')

    app = Flask(__name__, template_folder=tmpl, static_folder=stat)
    app.config.from_object(Config)

    # Ensure upload folder exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(os.path.join(base, '..', 'instance'), exist_ok=True)

    # Extensions
    db.init_app(app)
    migrate.init_app(app, db)
    CORS(app, resources={r"/*": {"origins": "*"}})

    # WebSocket via flask-socketio
    if HAS_SOCKETIO and socketio is not None:
        socketio.init_app(app, cors_allowed_origins='*',
                          async_mode='threading',
                          logger=False, engineio_logger=False)
        print('[init] SocketIO initialized (threading mode).')
    else:
        print('[init] flask-socketio not installed — real-time feed disabled.')

    # Wire Celery config so CELERY_TASK_ALWAYS_EAGER propagates
    try:
        from app.celery_init import celery_app, make_celery
        celery_app.config_from_object(app.config, namespace='CELERY')
        # Re-apply task_always_eager from Flask config
        celery_app.conf.update(
            task_always_eager=app.config.get('CELERY_TASK_ALWAYS_EAGER', True),
            task_eager_propagates=app.config.get('CELERY_TASK_EAGER_PROPAGATES', True),
        )
    except Exception as e:
        print(f"[init] Celery config warning: {e}")

    # Blueprints
    from app.routes import resume, jobs, matching, applications, profile
    from app.routes import ws_events
    app.register_blueprint(resume.bp)
    app.register_blueprint(jobs.bp)
    app.register_blueprint(matching.bp)
    app.register_blueprint(applications.bp)
    app.register_blueprint(profile.bp)

    @app.route('/')
    def index():
        from flask import redirect, url_for
        return redirect(url_for('jobs.jobs_page'))

    # Create tables on first run
    with app.app_context():
        db.create_all()
        _ensure_guest_user()
        _seed_sample_jobs()

    return app


def _ensure_guest_user():
    """Ensure a default guest user exists for the public app."""
    from app.models import User, Profile
    guest = User.query.get(1)
    if not guest:
        guest = User(id=1, email='guest@example.com', full_name='Guest User')
        guest.set_password('password-not-used')
        db.session.add(guest)
        db.session.flush()
        
        profile = Profile(user_id=guest.id, summary='Public Guest Profile')
        db.session.add(profile)
        db.session.commit()
        print("[init] Created default guest user.")

def _seed_sample_jobs():
    """Seed a handful of sample jobs so the UI is not empty on first run."""
    from app.models import Job
    if Job.query.count() > 0:
        return

    from datetime import datetime, timedelta
    import random

    samples = [
        ("Python Backend Developer", "DeepMind", "London, UK", "full-time", "remote",
         "We are looking for a skilled Python Backend Developer to build scalable APIs. "
         "Responsibilities include designing REST APIs with FastAPI/Flask, working with PostgreSQL, "
         "implementing CI/CD pipelines, and collaborating with ML engineers.",
         "Python, FastAPI, Flask, PostgreSQL, Docker, Redis, REST API, Git, CI/CD", 70000, 110000),
        ("Machine Learning Engineer", "OpenAI", "San Francisco, CA", "full-time", "hybrid",
         "Build and deploy production ML models. Work on LLM fine-tuning, "
         "data pipelines, model evaluation and monitoring.",
         "Python, PyTorch, TensorFlow, scikit-learn, Docker, Kubernetes, MLflow, SQL", 120000, 180000),
        ("Full Stack Developer", "Stripe", "Remote", "full-time", "remote",
         "Join our payments team. Build new product features end-to-end in React and Node.js. "
         "Write high-quality, tested code and participate in code reviews.",
         "React, Node.js, TypeScript, PostgreSQL, GraphQL, Docker, AWS, Jest", 90000, 140000),
        ("Data Scientist", "Netflix", "Los Gatos, CA", "full-time", "hybrid",
         "Analyse viewing data to drive product decisions. Build A/B testing frameworks, "
         "recommendation models, and reporting dashboards.",
         "Python, R, SQL, scikit-learn, Spark, Tableau, Statistics, A/B Testing", 100000, 150000),
        ("DevOps Engineer", "Cloudflare", "Remote", "full-time", "remote",
         "Own our infrastructure as code. Manage Kubernetes clusters, CI/CD pipelines, "
         "monitoring, alerting and incident response.",
         "Kubernetes, Terraform, AWS, GCP, Docker, Prometheus, Grafana, Ansible, Bash", 85000, 130000),
        ("Frontend Engineer", "Figma", "New York, NY", "full-time", "onsite",
         "Build beautiful, accessible UIs for the world's leading design tool. "
         "Work closely with designers to implement pixel-perfect experiences.",
         "React, TypeScript, CSS, WebGL, GraphQL, Jest, Webpack, Accessibility", 95000, 145000),
        ("iOS Developer", "Spotify", "Stockholm, Sweden", "full-time", "hybrid",
         "Work on the Spotify iOS app used by 400+ million users. "
         "Implement new features, optimise performance, and write unit tests.",
         "Swift, SwiftUI, Objective-C, Xcode, REST API, MVVM, Core Data", 80000, 120000),
        ("Cybersecurity Analyst", "Palantir", "Washington DC", "full-time", "onsite",
         "Monitor security events, perform threat hunting, conduct penetration tests, "
         "and develop security tooling for government clients.",
         "SIEM, Wireshark, Python, Kali Linux, Penetration Testing, OWASP, Splunk", 90000, 135000),
        ("NLP Engineer", "Hugging Face", "Remote", "full-time", "remote",
         "Improve and extend the Transformers library. Work on model training, "
         "dataset curation, and open-source community support.",
         "Python, HuggingFace, PyTorch, NLP, Transformers, BERT, GPT, LLM", 100000, 155000),
        ("Product Manager", "Notion", "Remote", "full-time", "remote",
         "Own product roadmap for collaboration features. Run user research, "
         "define requirements, work daily with engineering and design.",
         "Product Management, Roadmapping, SQL, A/B Testing, User Research, Figma, Agile", 110000, 160000),
    ]

    jobs = []
    for i, (title, company, location, jtype, rtype, desc, skills_str, sal_min, sal_max) in enumerate(samples):
        job = Job(
            title=title, company=company, location=location,
            job_type=jtype, remote_type=rtype,
            description=desc,
            required_skills=[s.strip() for s in skills_str.split(',')],
            salary_min=sal_min, salary_max=sal_max,
            source='seed',
            url=f'https://example.com/jobs/{i+1}',
            posted_date=datetime.utcnow() - timedelta(days=random.randint(0, 14))
        )
        jobs.append(job)

    db.session.add_all(jobs)
    db.session.commit()
    print(f'[seed] Inserted {len(jobs)} sample jobs.')
