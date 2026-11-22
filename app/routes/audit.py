import json

from flask import Blueprint, render_template, request

from app.models.audit_log import AuditLog
from app.models.user import ROLE_ADMIN, ROLE_AUDITOR
from app.security import role_required


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


@audit_bp.route("/")
@role_required(ROLE_ADMIN, ROLE_AUDITOR)
def logs():
    query = AuditLog.query
    action = (request.args.get("action") or "").strip()[:80]
    actor = (request.args.get("actor") or "").strip()[:80]
    if action:
        query = query.filter(AuditLog.action == action)
    if actor:
        query = query.filter(AuditLog.actor_username.ilike(f"%{actor}%"))

    entries = (
        query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(500).all()
    )

    rows = []
    for entry in entries:
        details = _pretty_details(entry.details_json)
        rows.append(
            {
                "id": entry.id,
                "created_at": entry.created_at,
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
        )

    return render_template(
        "admin/audit.html",
        entries=rows,
        action_filter=action,
        actor_filter=actor,
        action_options=sorted(ACTION_LABELS),
    )
