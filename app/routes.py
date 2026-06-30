from functools import wraps
from datetime import datetime

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    session,
    jsonify,
    current_app,
)

from services.resubmit_service import ResubmitService

main_bp = Blueprint('main', __name__)


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('main.login'))
        return f(*args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@main_bp.route('/', methods=['GET'])
def index():
    """Redirect root to login or search depending on session state."""
    if session.get('logged_in'):
        return redirect(url_for('main.search'))
    return redirect(url_for('main.login'))


@main_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Login page."""
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        expected_user = current_app.config.get('APP_USERNAME', 'admin')
        expected_pass = current_app.config.get('APP_PASSWORD', 'admin123')

        if username == expected_user and password == expected_pass:
            session['logged_in'] = True
            session['username'] = username
            return redirect(url_for('main.search'))
        else:
            error = 'Invalid username or password. Please try again.'

    return render_template('login.html', error=error)


@main_bp.route('/logout')
def logout():
    """Clear session and redirect to login."""
    session.clear()
    return redirect(url_for('main.login'))


@main_bp.route('/search', methods=['GET', 'POST'])
@login_required
def search():
    """Search page – accepts Case Number and/or GUID."""
    error = None
    if request.method == 'POST':
        case_number = request.form.get('case_number', '').strip()
        guid = request.form.get('guid', '').strip()

        if not case_number or not guid:
            error = 'Both Case Number and GUID are required to search.'
            return render_template('search.html', error=error)

        return redirect(
            url_for('main.resubmit_details', case_number=case_number, guid=guid)
        )

    return render_template('search.html', error=error)


@main_bp.route('/resubmit-details')
@login_required
def resubmit_details():
    """Display case resubmit details from Platform Support DB + TIBCO case data."""
    case_number = request.args.get('case_number', '').strip()
    guid = request.args.get('guid', '').strip()

    records, db_error = ResubmitService.fetch_case_records(case_number, guid)

    return render_template(
        'resubmit_details.html',
        records=records,
        case_number=case_number,
        guid=guid,
        db_error=db_error,
    )


@main_bp.route('/api/message-body')
@login_required
def message_body():
    """Return message body XML/JSON for a given record id (AJAX)."""
    record_id = request.args.get('id', '').strip()
    if not record_id:
        return jsonify({'error': 'No record id provided'}), 400

    body, err = ResubmitService.fetch_message_body(record_id)
    if err:
        return jsonify({'error': err}), 500

    return jsonify({'body': body})


@main_bp.route('/api/resubmit', methods=['POST'])
@login_required
def resubmit():
    """Handle the resubmit action for a case."""
    data = request.get_json(force=True) or {}
    case_number = data.get('case_number', '').strip()
    record_id = data.get('record_id', '').strip()
    reason = data.get('reason', '').strip()

    if not case_number or not reason:
        return jsonify({'success': False, 'error': 'Case number and reason are required.'}), 400

    success, message = ResubmitService.resubmit_case(
        case_number=case_number,
        record_id=record_id,
        reason=reason,
        submitted_by=session.get('username', 'unknown'),
    )

    if success:
        return jsonify({'success': True, 'message': message})
    return jsonify({'success': False, 'error': message}), 500
