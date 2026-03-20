import os
from flask import Blueprint, jsonify, request, render_template, current_app, send_file
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app import db
from app.models import User, Resume, Profile
from app.services.resume_parser import ResumeParser
from app.services.resume_generator import ResumeGenerator
import tempfile

bp = Blueprint('resume', __name__)
_parser    = None
_generator = None

def _get_parser():
    global _parser
    if _parser is None:
        _parser = ResumeParser(current_app.config.get('SKILLS_DB_PATH'))
    return _parser

def _get_generator():
    global _generator
    if _generator is None:
        _generator = ResumeGenerator(current_app.config.get('GEMINI_API_KEY', ''))
    return _generator

ALLOWED = {'.pdf', '.doc', '.docx', '.txt'}

def _allowed(filename):
    return os.path.splitext(filename)[1].lower() in ALLOWED


# ─────────────────────────────────────────
# Pages
# ─────────────────────────────────────────

@bp.route('/resume')
@login_required
def resume_page():
    resumes = Resume.query.filter_by(user_id=current_user.id).order_by(Resume.created_at.desc()).all()
    return render_template('resume.html', resumes=resumes)


# ─────────────────────────────────────────
# Upload & Parse
# ─────────────────────────────────────────

@bp.route('/api/resume/upload', methods=['POST'])
@login_required
def upload_resume():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400

    file = request.files['file']
    if not file.filename or not _allowed(file.filename):
        return jsonify({'error': 'Invalid file type. Use PDF, DOCX or TXT.'}), 400

    filename  = secure_filename(file.filename)
    upload_dir = current_app.config['UPLOAD_FOLDER']
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, f"1_{filename}")
    file.save(file_path)

    # Parse
    parser = _get_parser()
    parsed = parser.parse(file_path)

    if 'error' in parsed:
        return jsonify({'error': parsed['error']}), 422

    # Save to DB
    resume = Resume(
        user_id          = current_user.id,
        filename         = filename,
        file_path        = file_path,
        raw_text         = parsed.get('raw_text', ''),
        extracted_skills = parsed.get('skills', []),
        personal_info    = parsed.get('personal', {}),
    )
    db.session.add(resume)

    # Sync skills to profile
    user = current_user
    profile = user.profile
    if profile:
        existing = set(profile.skills or [])
        new      = set(parsed.get('skills', []))
        profile.skills = list(existing | new)

    db.session.commit()

    return jsonify({
        'success':  True,
        'resume_id': resume.id,
        'filename':  filename,
        'skills':    resume.extracted_skills,
        'personal':  resume.personal_info,
        'skill_count': len(resume.extracted_skills),
    })


@bp.route('/api/resume/list', methods=['GET'])
@login_required
def list_resumes():
    resumes = Resume.query.filter_by(user_id=current_user.id) \
                          .order_by(Resume.created_at.desc()).all()
    return jsonify([{
        'id':          r.id,
        'filename':    r.filename,
        'skills':      r.extracted_skills,
        'skill_count': len(r.extracted_skills or []),
        'created_at':  r.created_at.isoformat(),
    } for r in resumes])


# ─────────────────────────────────────────
# AI Resume Generation
# ─────────────────────────────────────────

@bp.route('/api/resume/generate', methods=['POST'])
@login_required
def generate_resume():
    data = request.get_json() or {}
    user = current_user
    profile = user.profile

    user_profile = {
        'full_name':  user.full_name,
        'email':      user.email,
        'phone':      user.phone or '',
        'summary':    profile.summary if profile else '',
        'skills':     profile.skills  if profile else [],
        'experience': profile.experience if profile else [],
        'education':  profile.education  if profile else [],
    }

    job_data = {
        'title':       data.get('job_title', 'Target Role'),
        'company':     data.get('company', 'Company'),
        'description': data.get('job_description', ''),
    }

    # Optionally look up by job_id
    if data.get('job_id'):
        from app.models import Job
        job = Job.query.get(data['job_id'])
        if job:
            job_data = {
                'title':       job.title,
                'company':     job.company,
                'description': job.description or '',
            }

    content = _get_generator().generate_tailored_resume(user_profile, job_data)
    return jsonify({'success': True, 'content': content})


@bp.route('/api/cover-letter/generate', methods=['POST'])
@login_required
def generate_cover_letter():
    data = request.get_json() or {}
    user = current_user
    profile = user.profile

    user_profile = {
        'full_name':  user.full_name,
        'email':      user.email,
        'skills':     profile.skills     if profile else [],
        'experience': profile.experience if profile else [],
    }

    job_data = {
        'title':       data.get('job_title', 'the role'),
        'company':     data.get('company', 'your company'),
        'description': data.get('job_description', ''),
    }

    if data.get('job_id'):
        from app.models import Job
        job = Job.query.get(data['job_id'])
        if job:
            job_data = {'title': job.title, 'company': job.company,
                        'description': job.description or ''}

    content = _get_generator().generate_cover_letter(user_profile, job_data)
    return jsonify({'success': True, 'content': content})


@bp.route('/api/resume/download', methods=['POST'])
@login_required
def download_resume():
    data    = request.get_json() or {}
    content = data.get('content', '')
    if not content:
        return jsonify({'error': 'No content'}), 400

    fd, path = tempfile.mkstemp(suffix='.md')
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(content)

    user = current_user
    name = (user.full_name or 'Resume').replace(' ', '_')
    return send_file(path, as_attachment=True,
                     download_name=f"Resume_{name}.md",
                     mimetype='text/markdown')
