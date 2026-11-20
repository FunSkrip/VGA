import os

from flask import Blueprint, abort, current_app, flash, redirect, render_template, url_for
from flask_login import current_user

from app.extensions import db
from app.forms.admin_forms import ActionForm, RoleChangeForm
from app.models.media_file import MediaFile
from app.models.user import ROLE_ADMIN, User
from app.security import audit_event, role_required


admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.route("/")
@role_required(ROLE_ADMIN)
def dashboard():
    return render_template(
        "admin/dashboard.html",
        users_count=User.query.count(),
        blocked_count=User.query.filter_by(is_blocked=True).count(),
        media_count=MediaFile.query.count(),
    )


@admin_bp.route("/users")
@role_required(ROLE_ADMIN)
def users():
    users_list = User.query.order_by(User.id.asc()).all()
    role_forms = {user.id: RoleChangeForm(prefix=f"role-{user.id}", role=user.role) for user in users_list}
    action_forms = {user.id: ActionForm(prefix=f"block-{user.id}") for user in users_list}
    return render_template(
        "admin/users.html",
        users=users_list,
        role_forms=role_forms,
        action_forms=action_forms,
    )


@admin_bp.route("/users/<int:user_id>/role", methods=["POST"])
@role_required(ROLE_ADMIN)
def change_role(user_id):
    target = db.session.get(User, user_id)
    if target is None:
        abort(404)
    if target.id == current_user.id:
        flash("Нельзя изменить собственную роль из этой панели.", "warning")
        return redirect(url_for("admin.users"))

    form = RoleChangeForm(prefix=f"role-{user_id}")
    if not form.validate_on_submit():
        flash("Некорректная форма изменения роли.", "danger")
        return redirect(url_for("admin.users"))

    new_role = form.role.data
    if target.role == ROLE_ADMIN and new_role != ROLE_ADMIN:
        active_admins = User.query.filter_by(role=ROLE_ADMIN, is_blocked=False).count()
        if active_admins <= 1:
            flash("Нельзя понизить роль последнего активного администратора.", "danger")
            return redirect(url_for("admin.users"))

    old_role = target.role
    target.role = new_role
    db.session.commit()
    audit_event(
        "role_changed",
        target_type="user",
        target_id=target.id,
        details={"old_role": old_role, "new_role": new_role},
    )
    flash(f"Роль пользователя {target.username} изменена.", "success")
    return redirect(url_for("admin.users"))


@admin_bp.route("/users/<int:user_id>/toggle-block", methods=["POST"])
@role_required(ROLE_ADMIN)
def toggle_block(user_id):
    target = db.session.get(User, user_id)
    if target is None:
        abort(404)
    if target.id == current_user.id:
        flash("Нельзя заблокировать собственную учётную запись.", "warning")
        return redirect(url_for("admin.users"))

    form = ActionForm(prefix=f"block-{user_id}")
    if not form.validate_on_submit():
        flash("Некорректная форма изменения статуса.", "danger")
        return redirect(url_for("admin.users"))

    if target.role == ROLE_ADMIN and not target.is_blocked:
        active_admins = User.query.filter_by(role=ROLE_ADMIN, is_blocked=False).count()
        if active_admins <= 1:
            flash("Нельзя заблокировать последнего активного администратора.", "danger")
            return redirect(url_for("admin.users"))

    target.is_blocked = not target.is_blocked
    new_state = "blocked" if target.is_blocked else "unblocked"
    db.session.commit()
    audit_event(
        "user_block_status_changed",
        target_type="user",
        target_id=target.id,
        details={"state": new_state},
    )
    flash(f"Учётная запись {target.username}: {new_state}.", "success")
    return redirect(url_for("admin.users"))


@admin_bp.route("/files")
@role_required(ROLE_ADMIN)
def files():
    # Display metadata only; there is intentionally no preview of another user's media.
    records = MediaFile.query.order_by(MediaFile.created_at.desc()).limit(500).all()
    action_forms = {record.uid: ActionForm(prefix=f"delete-{record.uid}") for record in records}
    return render_template("admin/files.html", records=records, action_forms=action_forms)


@admin_bp.route("/files/<string:uid>/delete", methods=["POST"])
@role_required(ROLE_ADMIN)
def delete_user_file(uid):
    record = db.session.get(MediaFile, uid)
    if record is None:
        abort(404)

    form = ActionForm(prefix=f"delete-{uid}")
    if not form.validate_on_submit():
        flash("Некорректная форма удаления файла.", "danger")
        return redirect(url_for("admin.files"))

    owner_id = record.owner_id
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
    audit_event(
        "admin_media_cleanup",
        target_type="media",
        target_id=uid,
        details={"owner_id": owner_id, "content_viewed": False},
    )
    flash("Файлы обработки удалены без просмотра их содержимого.", "success")
    return redirect(url_for("admin.files"))
