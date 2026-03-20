from app.celery_init import celery_app
from app.services.auto_apply import AutoApplyBot
from app.models import Application, Job, User, JobMatch
from app.services.email_service import EmailService
from app import db
from flask import current_app
from datetime import datetime, date


@celery_app.task(name='app.tasks.execute_auto_apply', bind=True, max_retries=3)
def execute_auto_apply(self, application_id):
    """
    Celery task that actually runs the Playwright bot to auto-apply.
    """
    app_obj = Application.query.get(application_id)
    if not app_obj:
        return {'status': 'error', 'message': 'Application not found'}

    user = User.query.get(app_obj.user_id)
    job  = Job.query.get(app_obj.job_id)

    if not user or not job:
        return {'status': 'error', 'message': 'User or Job not found'}

    app_obj.status = 'reviewing'
    db.session.commit()

    bot = AutoApplyBot(headless=True)
    try:
        success = bot.apply_to_job(user.profile, job, app_obj)
        if success:
            app_obj.status     = 'submitted'
            app_obj.auto_applied = True
            db.session.commit()

            # Send email notification
            try:
                EmailService.send_application_notification(
                    user.email,
                    {
                        'title':    job.title,
                        'company':  job.company,
                        'location': job.location,
                        'url':      job.url,
                    }
                )
            except Exception as e:
                print(f"[execute_auto_apply] Warning: Could not send notification email: {e}")

            return {'status': 'success'}
        else:
            app_obj.status = 'failed'
            db.session.commit()
            return {'status': 'failure', 'message': 'Bot could not complete application'}

    except Exception as exc:
        app_obj.status = 'failed'
        db.session.commit()
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(name='app.tasks.auto_apply_loop')
def auto_apply_loop():
    """
    Hourly Celery task — automatically queues auto-apply for high-scoring matches.
    Iterates over all users with auto_apply_enabled.
    """
    from app.models import Profile, Resume
    from sqlalchemy import desc
    
    users = User.query.join(Profile).filter(Profile.auto_apply_enabled == True).all()
    results = []

    if not users:
        return 'No users with auto-apply enabled'

    for user in users:
        profile = user.profile
        threshold    = profile.auto_apply_match_threshold or 85
        daily_limit  = profile.applications_per_day or 5
        blacklisted  = {c.lower() for c in (profile.company_blacklist or [])}
        whitelisted  = {c.lower() for c in (profile.company_whitelist or [])}
        blockers     = [kw.lower() for kw in (profile.keyword_blockers or [])]

        today_start = datetime.combine(date.today(), datetime.min.time())
        already_today = Application.query.filter(
            Application.user_id == user.id,
            Application.auto_applied == True,
            Application.applied_at >= today_start,
        ).count()

        remaining_slots = daily_limit - already_today
        if remaining_slots <= 0:
            results.append(f'User {user.id}: Daily limit reached')
            continue

        applied_job_ids = {a.job_id for a in Application.query.filter_by(user_id=user.id).all()}
        resume_ids = [r.id for r in Resume.query.filter_by(user_id=user.id).all()]
        if not resume_ids:
            results.append(f'User {user.id}: No resumes')
            continue

        high_matches = (
            JobMatch.query
            .filter(JobMatch.resume_id.in_(resume_ids))
            .filter(JobMatch.match_score >= threshold)
            .order_by(desc(JobMatch.match_score))
            .all()
        )

        queued = 0
        skipped = 0
        for match in high_matches:
            if queued >= remaining_slots:
                break

            job = match.job
            if not job or not job.url:
                skipped += 1
                continue

            company_lower = job.company.lower()
            if company_lower in blacklisted or (whitelisted and company_lower not in whitelisted):
                skipped += 1
                continue

            title_desc = f"{job.title} {job.description or ''}".lower()
            if any(kw in title_desc for kw in blockers):
                skipped += 1
                continue

            if profile.stealth_mode:
                company_jobs = {a.job.company.lower() for a in
                                Application.query.filter_by(user_id=user.id).join(Job).all()
                                if a.job}
                if company_lower in company_jobs:
                    skipped += 1
                    continue

            if job.id in applied_job_ids:
                skipped += 1
                continue

            if not job.url or ('greenhouse.io' not in job.url and 'lever.co' not in job.url):
                skipped += 1
                continue

            app_obj = Application(
                user_id     = user.id,
                job_id      = job.id,
                match_score = match.match_score,
                status      = 'reviewing',
                auto_applied= False,
            )
            db.session.add(app_obj)
            db.session.flush()
            applied_job_ids.add(job.id)
            queued += 1

        db.session.commit()

        new_apps = Application.query.filter(
            Application.user_id == user.id,
            Application.status == 'reviewing',
            Application.auto_applied == False,
            Application.applied_at >= today_start,
        ).all()

        for a in new_apps:
            execute_auto_apply.delay(a.id)

        results.append({
            'user_id': user.id,
            'queued':  queued,
            'skipped': skipped,
            'daily_limit': daily_limit,
            'used_today': already_today + queued,
        })

    return results


@celery_app.task(name='app.tasks.daily_job_scrape')
def daily_job_scrape():
    """
    Periodic task to fetch jobs from Adzuna/Remotive/Lever/Greenhouse
    """
    from app.services.job_aggregator import JobAggregator
    from app.routes.jobs import _store_jobs

    agg = JobAggregator(
        adzuna_app_id =current_app.config.get('ADZUNA_APP_ID',  ''),
        adzuna_app_key=current_app.config.get('ADZUNA_APP_KEY', ''),
    )
    jobs = agg.fetch_all(query='software developer', location='remote', max_per_source=20)
    _store_jobs(jobs)
    # After scraping, trigger match loop so new jobs get scored immediately
    auto_apply_loop.delay()
    return f"Scraped {len(jobs)} jobs"


@celery_app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    # Scrape jobs every 4 hours
    sender.add_periodic_task(14400.0, daily_job_scrape.s(), name='scrape every 4 hours')
    # Auto-apply loop runs every hour
    sender.add_periodic_task(3600.0,  auto_apply_loop.s(),  name='auto-apply loop every hour')
