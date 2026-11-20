from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from app.detector import detect_and_process
from app.forms.admin_forms import UploadForm
from app.models.user import ROLE_ADMIN, ROLE_USER
from app.security import role_required


analysis = Blueprint("analysis", __name__)

YOLO_MODELS = [
    ("yolov8n.pt", "YOLOv8 Nano"),
    ("yolov8s.pt", "YOLOv8 Small"),
    ("yolov8m.pt", "YOLOv8 Medium"),
    ("yolov8l.pt", "YOLOv8 Large"),
    ("yolov8x.pt", "YOLOv8 X-Large"),
]


@analysis.route("/analysis")
@role_required(ROLE_USER, ROLE_ADMIN)
def analysis_page():
    return render_template("analysis.html", models=YOLO_MODELS, upload_form=UploadForm())


@analysis.route("/upload", methods=["POST"])
@role_required(ROLE_USER, ROLE_ADMIN)
def upload():
    if not UploadForm().validate_on_submit():
        abort(400, description="Некорректный или просроченный CSRF-токен.")
    return detect_and_process(request, allowed_models={filename for filename, _label in YOLO_MODELS})
