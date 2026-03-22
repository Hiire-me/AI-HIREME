from flask import Blueprint, render_template
from flask_login import login_required

bp = Blueprint('settings_page', __name__)


@bp.route('/settings')
@login_required
def settings_page():
    return render_template('settings.html')
