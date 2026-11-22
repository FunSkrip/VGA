"""RBAC helpers and security audit utilities for VGA."""
from functools import wraps
import json

from flask import abort, current_app, g, has_request_context, request
from flask_login import current_user, login_required

from app.extensions import db
from app.models.audit_log import AuditLog


def role_required(*allowed_roles):
    """Allow only authenticated users whose persisted role is explicitly listed."""
    allowed = frozenset(allowed_roles)

    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            role = getattr(current_user, "role", None)
            if role not in allowed:
                audit_event(
                    "access_denied",
                    target_type="route",
                    target_id=request.endpoint or request.path,
                    details={"required_roles": sorted(allowed), "actual_role": role},
                )
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator


def audit_event(action, *, target_type=None, target_id=None, details=None, actor=None):
    """Persist metadata only. Callers must not pass passwords, secrets or media contents."""
    try:
        user = actor
        if (
            user is None
            and has_request_context()
            and getattr(current_user, "is_authenticated", False)
        ):
            user = current_user

        safe_details = details or {}
        details_json = json.dumps(safe_details, ensure_ascii=False, separators=(",", ":"))
        # Keep log entries bounded even if a caller accidentally passes a large value.
        if len(details_json) > 4000:
            details_json = json.dumps({"truncated": True}, separators=(",", ":"))

        entry = AuditLog(
            actor_user_id=getattr(user, "id", None),
            actor_username=(getattr(user, "username", None) or None),
            request_id=(
                (getattr(g, "request_id", None) or None)
                if has_request_context()
                else None
            ),
            action=str(action)[:80],
            target_type=str(target_type)[:80] if target_type is not None else None,
            target_id=str(target_id)[:128] if target_id is not None else None,
            ip_address=(
                (request.remote_addr or "")[:64] if has_request_context() else None
            ),
            user_agent=(
                (request.user_agent.string or "")[:300]
                if has_request_context()
                else None
            ),
            details_json=details_json,
        )
        db.session.add(entry)
        db.session.commit()
    except Exception:
        db.session.rollback()
        # Logging failure must not expose details or interrupt the main application flow.
        current_app.logger.exception("Unable to write security audit event")
