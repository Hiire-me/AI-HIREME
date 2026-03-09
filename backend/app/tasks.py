from app.celery_init import celery_app
from app.services.auto_apply import AutoApplyBot
from app.models import Application, Job, User
from app import db
from flask import current_app

@celery_app.task(name='app.tasks.execute_auto_apply', bind=True, max_retries=3)
def execute_auto_apply(self, application_id):
    """
    Celery task that actually runs the Playwright bot to auto-apply.
    """
    app_obj = Application.query.get(application_id)
    if not app_obj:
        return {'status': 'error', 'message': 'Application not found'}
    
    user = User.query.get(app_obj.user_id)
    job = Job.query.get(app_obj.job_id)

    if not user or not job:
        return {'status': 'error', 'message': 'User or Job not found'}

    app_obj.status = 'reviewing'
    db.session.commit()

    bot = AutoApplyBot(headless=True)
    try:
        success = bot.apply_to_job(user.profile, job, app_obj)
        if success:
            app_obj.status = 'submitted'
            app_obj.auto_applied = True
            db.session.commit()
            return {'status': 'success'}
        else:
            app_obj.status = 'failed'
            db.session.commit()
            return {'status': 'failure', 'message': 'Bot could not complete application'}
    except Exception as exc:
        app_obj.status = 'failed'
        db.session.commit()
        # Retry in case of transient errors
        raise self.retry(exc=exc, countdown=60)

@celery_app.task(name='app.tasks.daily_job_scrape')
def daily_job_scrape():
    """
    Periodic task to fetch jobs from default Adzuna/Remotive/Lever/Greenhouse
    """
    from app.services.job_aggregator import JobAggregator
    from app.routes.jobs import _store_jobs
    
    agg = JobAggregator(
        adzuna_app_id=current_app.config.get('ADZUNA_APP_ID', ''),
        adzuna_app_key=current_app.config.get('ADZUNA_APP_KEY', '')
    )
    with current_app.app_context():
        jobs = agg.fetch_all(query='software developer', location='remote', max_per_source=20)
        _store_jobs(jobs)
    return f"Scraped {len(jobs)} jobs"

@celery_app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    # Runs every 4 hours
    sender.add_periodic_task(14400.0, daily_job_scrape.s(), name='scrape every 4 hours')

