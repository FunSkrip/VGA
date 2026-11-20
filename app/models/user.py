from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db, login_manager


ROLE_USER = "user"
ROLE_ADMIN = "admin"
ROLE_AUDITOR = "auditor"
ROLE_CHOICES = (
    (ROLE_USER, "Пользователь"),
    (ROLE_ADMIN, "Администратор"),
    (ROLE_AUDITOR, "Аудитор"),
)
ROLE_LABELS = {
    ROLE_USER: "Пользователь",
    ROLE_ADMIN: "Администратор",
    ROLE_AUDITOR: "Аудитор",
}


class User(UserMixin, db.Model):
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    # Role is never accepted from the registration form. New accounts are users.
    role = db.Column(db.String(20), nullable=False, default=ROLE_USER, server_default=ROLE_USER, index=True)
    is_blocked = db.Column(db.Boolean, nullable=False, default=False, server_default="0")

    @property
    def is_active(self):
        # Flask-Login refuses to restore/login blocked accounts.
        return not self.is_blocked

    @property
    def role_label(self):
        return ROLE_LABELS.get(self.role, "Неизвестная роль")

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return bool(self.password_hash) and check_password_hash(self.password_hash, password)


@login_manager.user_loader
def load_user(user_id):
    try:
        return db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None
