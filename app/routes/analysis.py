from flask import Blueprint, abort, render_template, request

from app.detector import detect_and_process
from app.forms.admin_forms import UploadForm
from app.model_registry import available_models
from app.models.user import ROLE_ADMIN, ROLE_USER
from app.security import role_required


analysis = Blueprint("analysis", __name__)


@analysis.route("/analysis")
@role_required(ROLE_USER, ROLE_ADMIN)
def analysis_page():
    models = [
        (model["filename"], model["display_name"]) for model in available_models()
    ]
    return render_template("analysis.html", models=models, upload_form=UploadForm())


@analysis.route("/upload", methods=["POST"])
@role_required(ROLE_USER, ROLE_ADMIN)
def upload():
    if not UploadForm().validate_on_submit():
        abort(400, description="Некорректный или просроченный CSRF-токен.")
    allowed_models = {model["filename"] for model in available_models()}
    return detect_and_process(request, allowed_models=allowed_models)
