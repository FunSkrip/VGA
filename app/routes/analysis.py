from flask import Blueprint, render_template, request
from flask_login import login_required
from app.detector import detect_and_process

analysis = Blueprint('analysis', __name__)


@analysis.route('/analysis')
def analysis_page():
    models = [
        ('yolov8n.pt', 'YOLOv8 Nano'),
        ('yolov8s.pt', 'YOLOv8 Small'),
        ('yolov8m.pt', 'YOLOv8 Medium'),
        ('yolov8l.pt', 'YOLOv8 Large'),
        ('yolov8x.pt', 'YOLOv8 X-Large')
    ]
    return render_template('analysis.html', models=models)


@analysis.route('/upload', methods=['POST'])
@login_required
def upload():
    return detect_and_process(request)
