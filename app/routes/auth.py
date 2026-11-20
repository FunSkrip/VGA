from flask import Blueprint, current_app, flash, redirect, render_template, url_for
from flask_login import current_user, login_user, logout_user, login_required

from app.extensions import db
from app.forms.auth_forms import LoginForm, RegistrationForm
from app.models.user import User, ROLE_USER
from app.security import audit_event


auth = Blueprint("auth", __name__)


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
            login_user(user)
            audit_event("login_success", target_type="user", target_id=user.id, actor=user)
            return redirect(url_for("main.index"))

        audit_event(
            "login_failed",
            target_type="authentication",
            target_id=email[:128],
            details={"reason": "invalid_credentials_or_blocked"},
            actor=None,
        )
        flash("Неверный email или пароль, либо учётная запись заблокирована.", "danger")

    return render_template("login.html", form=form)


@auth.route("/logout", methods=["POST", "GET"])
@login_required
def logout():
    user = current_user._get_current_object()
    audit_event("logout", target_type="user", target_id=user.id, actor=user)
    logout_user()
    flash("Вы вышли из системы.", "info")
    return redirect(url_for("main.index"))
