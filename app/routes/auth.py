from urllib.parse import urljoin, urlsplit

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user

from app.extensions import db
from app.forms.auth_forms import LoginForm, LogoutForm, RegistrationForm
from app.models.user import ROLE_USER, User
from app.security import audit_event


auth = Blueprint("auth", __name__)


def _safe_next_url(target):
    """Return a same-origin relative URL or None to prevent open redirects."""
    if not target:
        return None

    host = urlsplit(request.host_url)
    candidate = urlsplit(urljoin(request.host_url, target))
    if candidate.scheme not in {"http", "https"} or candidate.netloc != host.netloc:
        return None

    path = candidate.path or "/"
    if path in {"/login", "/register"}:
        return None

    result = path
    if candidate.query:
        result += f"?{candidate.query}"
    if candidate.fragment:
        result += f"#{candidate.fragment}"
    return result


@auth.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(
            username=form.username.data.strip(),
            email=form.email.data.strip().lower(),
            role=ROLE_USER,  # Never take role from client input.
            is_blocked=False,
        )
        user.set_password(form.password.data)
        try:
            db.session.add(user)
            db.session.commit()
            audit_event("user_registered", target_type="user", target_id=user.id, actor=user)
            flash("Регистрация прошла успешно! Теперь вы можете войти.", "success")
            return redirect(url_for("auth.login"))
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Registration failed")
            flash("Ошибка регистрации. Возможно, email или имя уже заняты.", "danger")

    return render_template("register.html", form=form)


@auth.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    form = LoginForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(form.password.data) and not user.is_blocked:
            next_url = _safe_next_url(
                request.args.get("next") or request.form.get("next")
            )
            # Rotate the browser session before granting an authenticated identity.
            session.clear()
            session.permanent = True
            login_user(user)
            audit_event("login_success", target_type="user", target_id=user.id, actor=user)
            return redirect(next_url or url_for("main.index"))

        audit_event(
            "login_failed",
            target_type="authentication",
            target_id=email[:128],
            details={"reason": "invalid_credentials_or_blocked"},
            actor=None,
        )
        flash("Неверный email или пароль, либо учётная запись заблокирована.", "danger")

    return render_template("login.html", form=form)


@auth.route("/logout", methods=["POST"])
@login_required
def logout():
    form = LogoutForm()
    if not form.validate_on_submit():
        abort(400, description="Некорректный CSRF-токен.")

    user = current_user._get_current_object()
    audit_event("logout", target_type="user", target_id=user.id, actor=user)
    logout_user()
    session.clear()
    flash("Вы вышли из системы.", "info")
    return redirect(url_for("main.index"))
