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
from app.security import role_required


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
    except (ModelIntegrityError, ModelRegistryError):
        current_app.logger.exception("Model verification failed: %s", filename)
        flash("Не удалось проверить модель.", "danger")
    else:
        if entry.get("status") == "verified":
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
        set_model_enabled(filename, enable)
    except (ModelIntegrityError, ModelRegistryError):
        current_app.logger.exception("Could not change model state: %s", filename)
        flash(
            "Нельзя включить модель: файл отсутствует или не прошёл проверку. "
            "Скачайте модель заново.",
            "danger",
        )
    else:
        state = "включена" if enable else "выключена"
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
        verify_registry_entry(filename)
        set_model_enabled(filename, True)
    except (ModelDownloadError, ModelIntegrityError, ModelRegistryError):
        current_app.logger.exception("Could not download model: %s", filename)
        flash(
            "Не удалось скачать или проверить модель. Проверьте сеть и повторите попытку.",
            "danger",
        )
    else:
        flash(
            f"Модель {filename} скачана, проверена и включена "
            f"({result['size']} байт).",
            "success",
        )
    return redirect(url_for("models_admin.index"))
