import csv
import io
import json
from datetime import datetime, timezone

from flask import Blueprint, Response, abort, current_app, render_template, request

from app.models.audit_log import AuditLog
from app.models.user import ROLE_ADMIN, ROLE_AUDITOR
from app.security import audit_event, role_required


audit_bp = Blueprint("audit", __name__, url_prefix="/audit")


ACTION_LABELS = {
    "user_registered": "Регистрация",
    "login_success": "Успешный вход",
    "login_failed": "Неудачный вход",
    "logout": "Выход",
    "access_denied": "Отказ в доступе",
    "role_changed": "Смена роли",
    "user_block_status_changed": "Блокировка аккаунта",
    "admin_media_cleanup": "Очистка файлов",
    "media_access_denied": "Отказ к файлу",
    "media_viewed": "Просмотр файла",
    "media_downloaded": "Скачивание файла",
    "media_deleted": "Удаление файла",
    "detection_started": "Старт детекции",
    "detection_completed": "Детекция завершена",
    "detection_failed": "Ошибка детекции",
    "chatbot_rate_limited": "Лимит чат-бота",
    "chatbot_request_rejected": "Запрос бота отклонён",
    "chatbot_circuit_open": "Бот временно отключён",
    "chatbot_unavailable": "Бот недоступен",
    "chatbot_api_error": "Ошибка Gemini",
    "chatbot_request_succeeded": "Ответ бота",
    "backup_created": "Резервная копия",
    "backup_restored": "Восстановление БД",
    "backup_failed": "Ошибка backup",
    "backup_verify_failed": "Ошибка проверки backup",
    "audit_exported": "Экспорт аудита",
    "upload_rejected": "Загрузка отклонена",
    "model_verified": "Модель проверена",
    "model_verify_failed": "Ошибка проверки модели",
    "model_enabled": "Модель включена",
    "model_disabled": "Модель выключена",
    "model_toggle_failed": "Ошибка переключения модели",
    "model_downloaded": "Модель скачана",
    "model_download_failed": "Ошибка скачивания модели",
}

ACTION_TONES = {
    "user_registered": "success",
    "login_success": "success",
    "login_failed": "danger",
    "logout": "secondary",
    "access_denied": "danger",
    "role_changed": "warning",
    "user_block_status_changed": "warning",
    "admin_media_cleanup": "warning",
    "media_access_denied": "danger",
    "media_viewed": "info",
    "media_downloaded": "primary",
    "media_deleted": "secondary",
    "detection_started": "info",
    "detection_completed": "success",
    "detection_failed": "danger",
    "chatbot_rate_limited": "warning",
    "chatbot_request_rejected": "warning",
    "chatbot_circuit_open": "warning",
    "chatbot_unavailable": "warning",
    "chatbot_api_error": "danger",
    "chatbot_request_succeeded": "success",
    "backup_created": "success",
    "backup_restored": "info",
    "backup_failed": "danger",
    "backup_verify_failed": "danger",
    "audit_exported": "info",
    "upload_rejected": "danger",
    "model_verified": "success",
    "model_verify_failed": "danger",
    "model_enabled": "success",
    "model_disabled": "secondary",
    "model_toggle_failed": "danger",
    "model_downloaded": "primary",
    "model_download_failed": "danger",
}


def _pretty_details(raw_details):
    """Return indented JSON for the table, or None when there is nothing to show."""
    if not raw_details:
        return None
    try:
        parsed = json.loads(raw_details)
    except (TypeError, ValueError):
        return str(raw_details)
    if not parsed:
        return None
    return json.dumps(parsed, ensure_ascii=False, indent=2)


def _csv_safe(value) -> str:
    text = "" if value is None else str(value)
    if text.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + text
    return text


def _filters():
    return (
        (request.args.get("action") or "").strip()[:80],
        (request.args.get("actor") or "").strip()[:80],
        (request.args.get("request_id") or "").strip()[:64],
    )


def _filtered_query(action, actor, request_id):
    query = AuditLog.query
    if action:
        query = query.filter(AuditLog.action == action)
    if actor:
        query = query.filter(AuditLog.actor_username.ilike(f"%{actor}%"))
    if request_id:
        query = query.filter(AuditLog.request_id == request_id)
    return query


def _entry_row(entry):
    details = _pretty_details(entry.details_json)
    return {
        "id": entry.id,
        "created_at": entry.created_at,
        "request_id": entry.request_id,
        "actor_username": entry.actor_username,
        "actor_user_id": entry.actor_user_id,
        "action": entry.action,
        "action_label": ACTION_LABELS.get(entry.action, entry.action),
        "action_tone": ACTION_TONES.get(entry.action, "secondary"),
        "target_type": entry.target_type,
        "target_id": entry.target_id,
        "ip_address": entry.ip_address,
        "details_pretty": details,
        "has_details": details is not None,
    }


@audit_bp.route("/")
@role_required(ROLE_ADMIN, ROLE_AUDITOR)
def logs():
    action, actor, request_id = _filters()
    entries = (
        _filtered_query(action, actor, request_id)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(500)
        .all()
    )
    rows = [_entry_row(entry) for entry in entries]

    return render_template(
        "admin/audit.html",
        entries=rows,
        action_filter=action,
        actor_filter=actor,
        request_id_filter=request_id,
        action_options=sorted(ACTION_LABELS),
    )


@audit_bp.route("/export")
@role_required(ROLE_ADMIN, ROLE_AUDITOR)
def export():
    export_format = (request.args.get("format") or "csv").strip().lower()
    if export_format not in {"csv", "json"}:
        abort(400, description="Формат экспорта должен быть csv или json.")

    action, actor, request_id = _filters()
    limit = max(1, int(current_app.config.get("AUDIT_EXPORT_LIMIT", 10_000)))
    entries = (
        _filtered_query(action, actor, request_id)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(limit + 1)
        .all()
    )
    truncated = len(entries) > limit
    entries = entries[:limit]
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    if export_format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "id",
                "created_at",
                "request_id",
                "actor_user_id",
                "actor_username",
                "action",
                "target_type",
                "target_id",
                "ip_address",
                "user_agent",
                "details_json",
            ]
        )
        for entry in entries:
            writer.writerow(
                [
                    entry.id,
                    entry.created_at.isoformat(sep=" ", timespec="seconds"),
                    _csv_safe(entry.request_id),
                    _csv_safe(entry.actor_user_id),
                    _csv_safe(entry.actor_username),
                    _csv_safe(entry.action),
                    _csv_safe(entry.target_type),
                    _csv_safe(entry.target_id),
                    _csv_safe(entry.ip_address),
                    _csv_safe(entry.user_agent),
                    _csv_safe(entry.details_json),
                ]
            )
        response = Response(output.getvalue(), content_type="text/csv; charset=utf-8")
        response.headers["Content-Disposition"] = (
            f'attachment; filename="vga-audit-{timestamp}.csv"'
        )
    else:
        payload = []
        for entry in entries:
            try:
                details = json.loads(entry.details_json or "{}")
            except (TypeError, ValueError):
                details = entry.details_json
            payload.append(
                {
                    "id": entry.id,
                    "created_at": entry.created_at.isoformat(sep=" ", timespec="seconds"),
                    "request_id": entry.request_id,
                    "actor_user_id": entry.actor_user_id,
                    "actor_username": entry.actor_username,
                    "action": entry.action,
                    "target_type": entry.target_type,
                    "target_id": entry.target_id,
                    "ip_address": entry.ip_address,
                    "user_agent": entry.user_agent,
                    "details": details,
                }
            )
        response = Response(
            json.dumps(payload, ensure_ascii=False, indent=2),
            mimetype="application/json",
        )
        response.headers["Content-Disposition"] = (
            f'attachment; filename="vga-audit-{timestamp}.json"'
        )

    response.headers["Cache-Control"] = "no-store"
    if truncated:
        response.headers["X-Audit-Export-Truncated"] = "1"

    audit_event(
        "audit_exported",
        target_type="audit",
        target_id=export_format,
        details={
            "format": export_format,
            "action": action or None,
            "actor": actor or None,
            "request_id": request_id or None,
            "rows": len(entries),
            "truncated": truncated,
        },
    )
    return response
