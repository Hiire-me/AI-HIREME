from celery import Celery
import os

def make_celery(app=None):
    celery = Celery(
        app.import_name if app else 'app',
        broker=app.config['CELERY_BROKER_URL'] if app else os.environ.get('REDIS_URL', 'redis://localhost:6379/0'),
        backend=app.config['CELERY_RESULT_BACKEND'] if app else os.environ.get('REDIS_URL', 'redis://localhost:6379/0'),
        include=['app.tasks']
    )
    if app:
        celery.conf.update(app.config)
        
        class ContextTask(celery.Task):
            def __call__(self, *args, **kwargs):
                with app.app_context():
                    return self.run(*args, **kwargs)

        celery.Task = ContextTask
    return celery

# Module-level celery_app created without a Flask app context.
# It gets properly configured in create_app() via celery.conf.update(app.config).
# CELERY_TASK_ALWAYS_EAGER=True (set in config.py when no REDIS_URL env var)
# ensures tasks run synchronously in development/Windows without Redis.
celery_app = make_celery()
