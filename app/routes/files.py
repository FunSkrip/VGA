from flask import Blueprint, send_from_directory, current_app
from flask_login import login_required

files_bp = Blueprint('files', __name__)


@files_bp.route('/download/<filename>')
@login_required
def download_file(filename):
    return send_from_directory(
        directory=current_app.config['UPLOAD_FOLDER'],
        path=filename,
        as_attachment=True
    )
