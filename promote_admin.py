"""Promote an existing VGA account to administrator.

Run from the project root:
    python promote_admin.py user@example.com
"""
import sys

from app import create_app
from app.extensions import db
from app.models.user import ROLE_ADMIN, User


def main():
    if len(sys.argv) != 2:
        print("Usage: python promote_admin.py <registered-email>")
        return 2

    email = sys.argv[1].strip().lower()
    app = create_app()
    with app.app_context():
        user = User.query.filter(db.func.lower(User.email) == email).first()
        if user is None:
            print("Пользователь не найден. Сначала зарегистрируйте учётную запись в VGA.")
            return 1
        user.role = ROLE_ADMIN
        user.is_blocked = False
        db.session.commit()
        print(f"Учётная запись {user.email} получила роль Администратор.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
