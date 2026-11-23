"""Administrator UI for official YOLO models.

Deletion and arbitrary .pt uploads are intentionally not implemented. An admin
can download an official manifest model, verify it, enable/disable it and
restore a missing or damaged file.
"""
from flask import Blueprint, abort, current_app, flash, redirect, render_template, url_for

from app.forms.admin_forms import ActionForm
from app.model_download import ModelDownloadError, download_official_model
from app.model_integrity import ModelIntegrityError
from app.model_registry import (
    ModelRegistryError,
    get_admin_models,
    set_model_enabled,
    verify_registry_entry,
)
from app.models.user import ROLE_ADMIN
from app.security import audit_event, role_required


models_admin_bp = Blueprint("models_admin", __name__, url_prefix="/admin/models")


def _prefix(action: str, filename: str) -> str:
    return f"{action}-{filename.replace('.', '-')}"


def _entry_or_404(filename: str) -> dict:
    entry = next(
        (
            item
            for item in get_admin_models(refresh_status=False)
            if item["filename"] == filename
        ),
        None,
    )
    if entry is None:
        abort(404)
    return entry


@models_admin_bp.route("/")
@role_required(ROLE_ADMIN)
def index():
    records = get_admin_models(refresh_status=True)
    verify_forms = {
        record["filename"]: ActionForm(prefix=_prefix("verify", record["filename"]))
        for record in records
    }
    toggle_forms = {
        record["filename"]: ActionForm(prefix=_prefix("toggle", record["filename"]))
        for record in records
    }
    download_forms = {
        record["filename"]: ActionForm(prefix=_prefix("download", record["filename"]))
        for record in records
    }
    return render_template(
        "admin/models.html",
        records=records,
        verify_forms=verify_forms,
        toggle_forms=toggle_forms,
        download_forms=download_forms,
    )


@models_admin_bp.route("/<string:filename>/verify", methods=["POST"])
@role_required(ROLE_ADMIN)
def verify(filename):
    _entry_or_404(filename)
    form = ActionForm(prefix=_prefix("verify", filename))
    if not form.validate_on_submit():
        abort(400, description="Некорректный CSRF-токен.")

    try:
        entry = verify_registry_entry(filename)
    except (ModelIntegrityError, ModelRegistryError) as exc:
        current_app.logger.exception("Model verification failed: %s", filename)
        audit_event(
            "model_verify_failed",
            target_type="model",
            target_id=filename,
            details={"error_type": type(exc).__name__},
        )
        flash("Не удалось проверить модель.", "danger")
    else:
        status = entry.get("status")
        audit_details = {
            "status": status,
            "sha256": entry.get("sha256"),
            "size": entry.get("size"),
        }
        if status == "verified":
            audit_event(
                "model_verified",
                target_type="model",
                target_id=filename,
                details=audit_details,
            )
        else:
            audit_details["error_type"] = "integrity_check_failed"
            audit_event(
                "model_verify_failed",
                target_type="model",
                target_id=filename,
                details=audit_details,
            )
        if status == "verified":
            flash(f"Модель {filename} прошла проверку SHA-256.", "success")
        else:
            flash(
                f"Модель {filename} отсутствует или повреждена. Скачайте её заново.",
                "danger",
            )
    return redirect(url_for("models_admin.index"))


@models_admin_bp.route("/<string:filename>/toggle", methods=["POST"])
@role_required(ROLE_ADMIN)
def toggle(filename):
    entry = _entry_or_404(filename)
    form = ActionForm(prefix=_prefix("toggle", filename))
    if not form.validate_on_submit():
        abort(400, description="Некорректный CSRF-токен.")

    enable = not bool(entry.get("enabled"))
    try:
        updated = set_model_enabled(filename, enable)
    except (ModelIntegrityError, ModelRegistryError) as exc:
        current_app.logger.exception("Could not change model state: %s", filename)
        audit_event(
            "model_toggle_failed",
            target_type="model",
            target_id=filename,
            details={
                "requested_state": "enabled" if enable else "disabled",
                "error_type": type(exc).__name__,
            },
        )
        flash(
            "Нельзя включить модель: файл отсутствует или не прошёл проверку. "
            "Скачайте модель заново.",
            "danger",
        )
    else:
        state = "включена" if enable else "выключена"
        audit_event(
            "model_enabled" if enable else "model_disabled",
            target_type="model",
            target_id=filename,
            details={
                "status": updated.get("status"),
                "sha256": updated.get("sha256"),
                "size": updated.get("size"),
            },
        )
        flash(f"Модель {filename} {state}.", "success")
    return redirect(url_for("models_admin.index"))


@models_admin_bp.route("/<string:filename>/download", methods=["POST"])
@role_required(ROLE_ADMIN)
def download(filename):
    _entry_or_404(filename)
    form = ActionForm(prefix=_prefix("download", filename))
    if not form.validate_on_submit():
        abort(400, description="Некорректный CSRF-токен.")

    try:
        result = download_official_model(filename)
        entry = verify_registry_entry(filename)
        set_model_enabled(filename, True)
    except (ModelDownloadError, ModelIntegrityError, ModelRegistryError) as exc:
        current_app.logger.exception("Could not download model: %s", filename)
        audit_event(
            "model_download_failed",
            target_type="model",
            target_id=filename,
            details={"error_type": type(exc).__name__},
        )
        flash(
            "Не удалось скачать или проверить модель. Проверьте сеть и повторите попытку.",
            "danger",
        )
    else:
        audit_event(
            "model_downloaded",
            target_type="model",
            target_id=filename,
            details={
                "size": result["size"],
                "sha256": result["sha256"],
                "status": entry.get("status"),
            },
        )
        flash(
            f"Модель {filename} скачана, проверена и включена "
            f"({result['size']} байт).",
            "success",
        )
    return redirect(url_for("models_admin.index"))
