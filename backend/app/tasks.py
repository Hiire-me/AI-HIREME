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

    Logic (per spec):
        > threshold  → auto-apply immediately
        0.70–threshold → add to approval queue (status='pending')
        < 0.70       → skip
    """
    user = User.query.get(1)
    if not user:
        return 'No user found'

    profile = user.profile
    if not profile or not profile.auto_apply_enabled:
        return 'Auto-apply is disabled for this user'

    threshold    = profile.auto_apply_match_threshold or 85
    daily_limit  = profile.applications_per_day or 5
    blacklisted  = {c.lower() for c in (profile.company_blacklist or [])}
    whitelisted  = {c.lower() for c in (profile.company_whitelist or [])}
    blockers     = [kw.lower() for kw in (profile.keyword_blockers or [])]

    # Count how many auto-applications have been created today
    today_start = datetime.combine(date.today(), datetime.min.time())
    already_today = Application.query.filter(
        Application.user_id == 1,
        Application.auto_applied == True,
        Application.applied_at >= today_start,
    ).count()

    remaining_slots = daily_limit - already_today
    if remaining_slots <= 0:
        return f'Daily auto-apply limit ({daily_limit}) reached'

    # Get already-applied job IDs to avoid duplicate applications
    applied_job_ids = {
        a.job_id for a in Application.query.filter_by(user_id=1).all()
    }

    # Fetch matches above threshold, ordered best-first
    from sqlalchemy import desc
    from app.models import Resume
    resume_ids = [r.id for r in Resume.query.filter_by(user_id=1).all()]
    if not resume_ids:
        return 'No resumes found — upload a resume first'

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

        # Rules Engine filters
        company_lower = job.company.lower()
        if company_lower in blacklisted:
            skipped += 1
            continue
        if whitelisted and company_lower not in whitelisted:
            skipped += 1
            continue

        title_desc = f"{job.title} {job.description or ''}".lower()
        if any(kw in title_desc for kw in blockers):
            skipped += 1
            continue

        # Stealth mode: skip if user already applied to this company manually
        if profile.stealth_mode:
            company_jobs = {a.job.company.lower() for a in
                            Application.query.filter_by(user_id=1).join(Job).all()
                            if a.job}
            if company_lower in company_jobs:
                skipped += 1
                continue

        # Skip jobs already applied to
        if job.id in applied_job_ids:
            skipped += 1
            continue

        # Only auto-apply to supported ATS platforms
        if not job.url or ('greenhouse.io' not in job.url and 'lever.co' not in job.url):
            skipped += 1
            continue

        # Create application and queue the bot
        app_obj = Application(
            user_id     = 1,
            job_id      = job.id,
            match_score = match.match_score,
            status      = 'reviewing',
            auto_applied= False,  # will be set to True after bot succeeds
        )
        db.session.add(app_obj)
        db.session.flush()
        applied_job_ids.add(job.id)
        queued += 1

    db.session.commit()

    # Queue Playwright tasks for newly created applications
    new_apps = Application.query.filter(
        Application.user_id == 1,
        Application.status == 'reviewing',
        Application.auto_applied == False,
        Application.applied_at >= today_start,
    ).all()

    for a in new_apps:
        execute_auto_apply.delay(a.id)

    return {
        'queued':  queued,
        'skipped': skipped,
        'daily_limit': daily_limit,
        'used_today': already_today + queued,
    }


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
