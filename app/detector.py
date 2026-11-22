"""YOLO media processing with private storage, ownership metadata and audit events."""

import os
import subprocess
import uuid

import cv2
import imageio
import imageio_ffmpeg
import numpy as np
from flask import current_app, flash, redirect, render_template, session, url_for
from flask_login import current_user
from ultralytics import YOLO
from werkzeug.utils import secure_filename

from app.extensions import db
from app.file_validation import (
    MAX_GIF_FRAMES,
    UnsupportedMediaError,
    enforce_gif_limits,
    enforce_image_pixel_limit,
    enforce_video_limits,
    validate_media_signature,
)
from app.forms.admin_forms import ActionForm
from app.model_integrity import ModelIntegrityError
from app.model_registry import ModelRegistryError, available_models, get_model_entry
from app.models.media_file import MediaFile
from app.security import audit_event


ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "mp4", "avi", "mov"}
CLASS_RU = {"person": "Human", "car": "Car"}
YOLO_CACHE = {}

# Optional custom tracker configuration. Keep this file at
# app/trackers/botsort_vga.yaml. It should have with_reid: False for the
# YOLO26/Ultralytics combination that produced the tensor-index error.
TRACKER_CONFIG = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "trackers",
    "botsort_vga.yaml",
)


def load_model(model_filename):
    """Load an enabled model only after its SHA-256 has been verified.

    Ultralytics is intentionally never asked to download weights here: a .pt
    file is a pickle and must be verified before PyTorch deserializes it.
    """
    entry = get_model_entry(model_filename)
    cache_key = (model_filename, entry["sha256"])
    cached = YOLO_CACHE.get(model_filename)
    if cached is not None and cached[0] == cache_key:
        return cached[1]

    model_path = entry["absolute_path"]
    current_app.logger.info("Loading verified YOLO model: %s", model_path)
    model = YOLO(model_path)
    YOLO_CACHE[model_filename] = (cache_key, model)
    return model


def reset_tracker(model):
    """Reset cached tracker state before processing a different GIF/video."""
    predictor = getattr(model, "predictor", None)
    trackers = getattr(predictor, "trackers", None)

    if trackers:
        for tracker in trackers:
            reset = getattr(tracker, "reset", None)
            if callable(reset):
                reset()


def _cleanup(*paths):
    for path in paths:
        try:
            if path and os.path.isfile(path):
                os.remove(path)
        except OSError:
            current_app.logger.exception("Could not clean temporary media file")


def _audit_safely(event_name, *, target_type=None, target_id=None, details=None):
    """Do not let an audit-storage failure mask the media-processing outcome."""
    try:
        audit_event(
            event_name,
            target_type=target_type,
            target_id=target_id,
            details=details or {},
        )
    except Exception:
        current_app.logger.exception("Could not write audit event: %s", event_name)
        db.session.rollback()


def _convert_mp4_for_browser(raw_video_path, output_path):
    """Transcode the OpenCV mp4v output to browser-friendly H.264 MP4."""
    ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
    timeout_seconds = int(current_app.config.get("FFMPEG_TIMEOUT_SECONDS", 1800))

    command = [
        ffmpeg_path,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        raw_video_path,
        "-map",
        "0:v:0",
        "-an",  # Current OpenCV VideoWriter pipeline does not preserve audio.
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "23",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        output_path,
    ]

    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        current_app.logger.error(
            "FFmpeg timed out after %s seconds while transcoding result video",
            timeout_seconds,
        )
        raise RuntimeError("Превышено время конвертации видео") from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        current_app.logger.error("FFmpeg video conversion failed: %s", stderr[-4000:])
        raise RuntimeError("Не удалось подготовить видео для просмотра") from exc

    if not os.path.isfile(output_path) or os.path.getsize(output_path) == 0:
        raise RuntimeError("FFmpeg не создал итоговый видеофайл")

    return completed


def detect_and_process(request, allowed_models=None):
    """Process one upload and save its result outside Flask's public static folder."""
    uid = uuid.uuid4().hex
    upload_dir = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(upload_dir, exist_ok=True)
    src_path = res_path = raw_video_path = None
    cap = None
    out = None
    record_committed = False

    # Long-running detection must not lose the session that started it.
    session.modified = True

    try:
        file_storage = request.files.get("file")
        if file_storage is None or not file_storage.filename:
            flash("Выберите файл для обработки.", "warning")
            return redirect(url_for("analysis.analysis_page"))

        safe_original = secure_filename(file_storage.filename)
        if not safe_original or "." not in safe_original:
            flash("Не удалось определить имя или формат файла.", "danger")
            return redirect(url_for("analysis.analysis_page"))

        ext = safe_original.rsplit(".", 1)[-1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            flash("Формат файла не поддерживается.", "danger")
            return redirect(url_for("analysis.analysis_page"))

        model_name = (request.form.get("model") or "").strip()
        if allowed_models is None:
            accepted_models = {model["filename"] for model in available_models()}
        else:
            accepted_models = set(allowed_models)
        if model_name not in accepted_models:
            flash("Выбрана недопустимая модель YOLO.", "danger")
            return redirect(url_for("analysis.analysis_page"))

        src_filename = f"src_{uid}.{ext}"
        result_ext = "mp4" if ext in {"mp4", "avi", "mov"} else ext
        res_filename = f"res_{uid}.{result_ext}"
        src_path = os.path.join(upload_dir, src_filename)
        res_path = os.path.join(upload_dir, res_filename)
        file_storage.save(src_path)

        size = os.path.getsize(src_path)
        max_bytes = current_app.config.get("MAX_CONTENT_LENGTH") or (250 * 1024 * 1024)
        if size <= 0 or size > max_bytes:
            raise ValueError("Размер файла недопустим")

        # Extensions are client-controlled; verify the real container first.
        validate_media_signature(src_path, ext)

        _audit_safely(
            "detection_started",
            target_type="media",
            target_id=uid,
            details={"extension": ext, "model": model_name, "size_bytes": size},
        )

        yolo = load_model(model_name)
        id_map = {}
        next_label = 1
        counts = {"person": set(), "car": set()}

        if ext in {"jpg", "jpeg", "png"}:
            # np.fromfile + imdecode handles some Windows path/encoding cases
            # that cv2.imread does not handle reliably.
            image_data = np.fromfile(src_path, dtype=np.uint8)
            img = cv2.imdecode(image_data, cv2.IMREAD_COLOR)
            if img is None or img.size == 0:
                current_app.logger.error(
                    "OpenCV could not decode image: path=%s size=%s",
                    src_path,
                    os.path.getsize(src_path) if os.path.isfile(src_path) else "missing",
                )
                raise ValueError("Не удалось декодировать изображение")

            enforce_image_pixel_limit(img.shape[1], img.shape[0])
            reset_tracker(yolo)
            result = yolo(img, classes=[0, 2], verbose=False)[0]
            image_counts = {"person": 0, "car": 0}
            for box in result.boxes:
                cls = int(box.cls.cpu().numpy())
                name_en = yolo.names[cls]
                if name_en not in image_counts:
                    continue

                name_ru = CLASS_RU.get(name_en, name_en)
                x1, y1, x2, y2 = map(int, box.xyxy[0].cpu().numpy())
                cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(
                    img,
                    name_ru,
                    (x1, max(15, y1 - 10)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 255, 0),
                    2,
                )
                image_counts[name_en] += 1

            if not cv2.imwrite(res_path, img):
                raise RuntimeError("Не удалось сохранить изображение")
            people, cars = image_counts["person"], image_counts["car"]

        elif ext == "gif":
            enforce_gif_limits(src_path)
            frames = imageio.mimread(src_path)
            if not frames:
                raise ValueError("GIF не содержит кадров")
            if len(frames) > MAX_GIF_FRAMES:
                raise UnsupportedMediaError("GIF содержит слишком много кадров")

            reset_tracker(yolo)
            processed = []
            for frame in frames:
                img = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                det = yolo.track(
                    img,
                    classes=[0, 2],
                    tracker=TRACKER_CONFIG,
                    persist=True,
                    verbose=False,
                )[0]

                for box in det.boxes:
                    cls = int(box.cls.cpu().numpy())
                    name_en = yolo.names[cls]
                    if name_en not in counts:
                        continue

                    name_ru = CLASS_RU.get(name_en, name_en)
                    raw_id = getattr(box, "id", None)
                    if raw_id is not None:
                        obj_id = int(raw_id.cpu().numpy())
                        if obj_id not in id_map:
                            id_map[obj_id] = next_label
                            next_label += 1
                        label = f"{name_ru} #{id_map[obj_id]}"
                        counts[name_en].add(obj_id)
                    else:
                        label = name_ru

                    x1, y1, x2, y2 = map(int, box.xyxy[0].cpu().numpy())
                    cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    cv2.putText(
                        img,
                        label,
                        (x1, max(15, y1 - 10)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.6,
                        (0, 255, 0),
                        2,
                    )

                footer = f"People: {len(counts['person'])}  Cars: {len(counts['car'])}"
                cv2.putText(
                    img,
                    footer,
                    (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1,
                    (0, 0, 255),
                    2,
                )
                processed.append(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))

            imageio.mimsave(res_path, processed, fps=10)
            people, cars = len(counts["person"]), len(counts["car"])

        else:
            cap = cv2.VideoCapture(src_path)
            if not cap.isOpened():
                raise ValueError("Не удалось открыть видео")

            fps = cap.get(cv2.CAP_PROP_FPS)
            if not fps or fps <= 0:
                fps = 25.0

            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
            enforce_video_limits(width, height, fps, frame_count)

            # OpenCV writes an intermediate MPEG-4 Part 2 file. FFmpeg converts
            # it afterwards to H.264/yuv420p for browser playback.
            raw_video_path = os.path.join(upload_dir, f"res_{uid}_raw.mp4")
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            out = cv2.VideoWriter(raw_video_path, fourcc, fps, (width, height))
            if not out.isOpened():
                raise RuntimeError("Не удалось открыть видеокодек для промежуточного видео")

            reset_tracker(yolo)
            try:
                while True:
                    ok, frame = cap.read()
                    if not ok:
                        break

                    det = yolo.track(
                        frame,
                        classes=[0, 2],
                        tracker=TRACKER_CONFIG,
                        persist=True,
                        verbose=False,
                    )[0]

                    for box in det.boxes:
                        cls = int(box.cls.cpu().numpy())
                        name_en = yolo.names[cls]
                        if name_en not in counts:
                            continue

                        name_ru = CLASS_RU.get(name_en, name_en)
                        raw_id = getattr(box, "id", None)
                        if raw_id is not None:
                            obj_id = int(raw_id.cpu().numpy())
                            if obj_id not in id_map:
                                id_map[obj_id] = next_label
                                next_label += 1
                            label = f"{name_ru} #{id_map[obj_id]}"
                            counts[name_en].add(obj_id)
                        else:
                            label = name_ru

                        x1, y1, x2, y2 = map(int, box.xyxy[0].cpu().numpy())
                        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                        cv2.putText(
                            frame,
                            label,
                            (x1, max(15, y1 - 10)),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.6,
                            (0, 255, 0),
                            2,
                        )

                    footer = f"People: {len(counts['person'])}  Cars: {len(counts['car'])}"
                    cv2.putText(
                        frame,
                        footer,
                        (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        1,
                        (0, 0, 255),
                        2,
                    )
                    out.write(frame)
            finally:
                if cap is not None:
                    cap.release()
                if out is not None:
                    out.release()

            _convert_mp4_for_browser(raw_video_path, res_path)
            _cleanup(raw_video_path)
            raw_video_path = None
            people, cars = len(counts["person"]), len(counts["car"])

        if not os.path.isfile(res_path) or os.path.getsize(res_path) == 0:
            raise RuntimeError("Результат обработки не был создан")

        record = MediaFile(
            uid=uid,
            owner_id=current_user.id,
            original_name=safe_original[:255],
            source_filename=src_filename,
            result_filename=res_filename,
            model_name=model_name,
            source_extension=ext,
            result_extension=result_ext,
            people_count=int(people),
            cars_count=int(cars),
        )
        db.session.add(record)
        db.session.commit()
        record_committed = True

        _audit_safely(
            "detection_completed",
            target_type="media",
            target_id=uid,
            details={"model": model_name, "people": int(people), "cars": int(cars)},
        )

        # Refresh the cookie on the response that delivers the completed result.
        session.modified = True
        return render_template(
            "result.html",
            uid=uid,
            people=people,
            cars=cars,
            result_extension=result_ext,
            delete_form=ActionForm(prefix=f"user-delete-{uid}"),
        )

    except Exception as exc:
        current_app.logger.exception(
            "VGA media processing failed (%s)", type(exc).__name__
        )
        db.session.rollback()

        # If the DB record was already committed, do not delete its result file.
        if not record_committed:
            _cleanup(src_path, res_path, raw_video_path)

        model_failure = isinstance(exc, (ModelIntegrityError, ModelRegistryError))
        media_failure = isinstance(exc, UnsupportedMediaError)
        if media_failure:
            reason = "invalid_media"
        elif model_failure:
            reason = "model_unavailable"
        else:
            reason = "processing"
        _audit_safely(
            "detection_failed",
            target_type="media",
            target_id=uid,
            details={"error_type": type(exc).__name__, "reason": reason},
        )
        if media_failure:
            flash(
                "Содержимое файла не соответствует поддерживаемому формату "
                "или превышает допустимые размеры.",
                "danger",
            )
        elif model_failure:
            flash(
                "Выбранная модель недоступна или не прошла проверку целостности. "
                "Обратитесь к администратору.",
                "danger",
            )
        else:
            flash(
                "Не удалось обработать файл. Проверьте формат и модель, затем попробуйте снова.",
                "danger",
            )
        return redirect(url_for("analysis.analysis_page"))
