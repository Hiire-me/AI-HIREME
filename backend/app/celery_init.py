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

# In some implementations, we create a default celery app directly for workers
from app import create_app
flask_app = create_app()
celery_app = make_celery(flask_app)
