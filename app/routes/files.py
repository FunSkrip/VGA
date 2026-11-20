import os

from flask import Blueprint, abort, current_app, redirect, send_from_directory, url_for, flash
from flask_login import current_user

from app.forms.admin_forms import ActionForm
from app.extensions import db
from app.models.media_file import MediaFile
from app.models.user import ROLE_ADMIN, ROLE_USER
from app.security import audit_event, role_required


files_bp = Blueprint("files", __name__)


def _owned_media_or_404(uid):
    record = db.session.get(MediaFile, uid)
    # Do not disclose whether another user's identifier exists.
    if record is None or record.owner_id != current_user.id:
        audit_event("media_access_denied", target_type="media", target_id=uid)
        abort(404)
    return record


def _private_file_response(record, filename, *, as_attachment):
    response = send_from_directory(
        directory=current_app.config["UPLOAD_FOLDER"],
        path=filename,
        as_attachment=as_attachment,
        conditional=True,
    )
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@files_bp.route("/media/<string:uid>")
@role_required(ROLE_USER, ROLE_ADMIN)
def view_media(uid):
    record = _owned_media_or_404(uid)
    audit_event("media_viewed", target_type="media", target_id=uid)
    return _private_file_response(record, record.result_filename, as_attachment=False)


@files_bp.route("/download/<string:uid>")
@role_required(ROLE_USER, ROLE_ADMIN)
def download_file(uid):
    record = _owned_media_or_404(uid)
    audit_event("media_downloaded", target_type="media", target_id=uid)
    return _private_file_response(record, record.result_filename, as_attachment=True)


@files_bp.route("/files/<string:uid>/delete", methods=["POST"])
@role_required(ROLE_USER, ROLE_ADMIN)
def delete_file(uid):
    record = _owned_media_or_404(uid)
    form = ActionForm(prefix=f"user-delete-{uid}")
    if not form.validate_on_submit():
        abort(400, description="Некорректный CSRF-токен.")

    paths = [
        os.path.join(current_app.config["UPLOAD_FOLDER"], record.source_filename),
        os.path.join(current_app.config["UPLOAD_FOLDER"], record.result_filename),
    ]
    for path in paths:
        try:
            if os.path.isfile(path):
                os.remove(path)
        except OSError:
            current_app.logger.exception("Could not remove private media file")

    db.session.delete(record)
    db.session.commit()
    audit_event("media_deleted", target_type="media", target_id=uid)
    flash("Результат и исходный файл удалены.", "success")
    return redirect(url_for("analysis.analysis_page"))
