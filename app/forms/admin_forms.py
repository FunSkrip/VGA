from flask_wtf import FlaskForm
from wtforms import SelectField, SubmitField
from wtforms.validators import DataRequired, AnyOf

from app.models.user import ROLE_CHOICES


class RoleChangeForm(FlaskForm):
    role = SelectField(
        "Роль",
        choices=list(ROLE_CHOICES),
        validators=[DataRequired(), AnyOf([role for role, _label in ROLE_CHOICES])],
    )
    submit = SubmitField("Сохранить роль")


class ActionForm(FlaskForm):
    submit = SubmitField("Подтвердить")


class UploadForm(FlaskForm):
    """CSRF-only form for the HTML file-upload form."""
    pass
