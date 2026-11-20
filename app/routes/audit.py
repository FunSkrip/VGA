from flask import Blueprint, render_template, request

from app.models.audit_log import AuditLog
from app.models.user import ROLE_ADMIN, ROLE_AUDITOR
from app.security import role_required


audit_bp = Blueprint("audit", __name__, url_prefix="/audit")


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
    entries = query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(500).all()
    return render_template("admin/audit.html", entries=entries, action_filter=action, actor_filter=actor)
