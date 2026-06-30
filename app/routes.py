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
    """Search page – both Case Number and GUID are mandatory."""
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
    """Display TIBCO case message details looked up by case number."""
    case_number = request.args.get('case_number', '').strip()
    guid = request.args.get('guid', '').strip()

    if not case_number:
        return redirect(url_for('main.search'))

    tibco_record, db_error = ResubmitService.fetch_tibco_case_message(case_number, guid)

    return render_template(
        'resubmit_details.html',
        tibco_record=tibco_record,
        case_number=case_number,
        guid=guid,
        db_error=db_error,
    )


@main_bp.route('/api/case-lookup')
@login_required
def case_lookup():
    """JSON API: look up TIBCO case message by case number and GUID."""
    case_number = request.args.get('case_number', '').strip()
    guid = request.args.get('guid', '').strip()
    if not case_number or not guid:
        return jsonify({'error': 'case_number and guid parameters are required'}), 400

    result, err = ResubmitService.fetch_tibco_case_message(case_number, guid)
    if result is None:
        return jsonify({'error': err}), 404

    return jsonify({'data': result, 'warning': err})


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


@main_bp.route('/api/amend-status', methods=['POST'])
@login_required
def amend_status():
    """Set MessageStatus = 1 for the given MessageIdentifier in WSD_Messages."""
    data = request.get_json(force=True) or {}
    message_identifier = data.get('message_identifier', '').strip()

    if not message_identifier:
        return jsonify({'success': False, 'error': 'message_identifier is required.'}), 400

    success, error = ResubmitService.amend_message_status(message_identifier)
    if success:
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': error}), 500


@main_bp.route('/api/resubmit', methods=['POST'])
@login_required
def resubmit():
    """Handle the resubmit action for a case."""
    data = request.get_json(force=True) or {}
    case_number  = data.get('case_number', '').strip()
    record_id    = data.get('record_id', '').strip()
    reason       = data.get('reason', '').strip()
    investor_id  = data.get('investor_id', '').strip()
    proc_name    = data.get('proc_name', '').strip()

    if not case_number or not reason:
        return jsonify({'success': False, 'error': 'Case number and reason are required.'}), 400

    success, message, queue, message_body, response_xml = ResubmitService.resubmit_case(
        case_number=case_number,
        record_id=record_id,
        reason=reason,
        submitted_by=session.get('username', 'unknown'),
        investor_id=investor_id,
        proc_name=proc_name,
    )

    if success:
        return jsonify({'success': True, 'message': message, 'queue': queue,
                        'message_body': message_body, 'response_xml': response_xml})
    return jsonify({'success': False, 'error': message, 'queue': queue,
                    'message_body': message_body}), 500
