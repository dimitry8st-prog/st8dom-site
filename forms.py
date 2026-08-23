"""WTForms: публичная заявка и вход в админку. CSRF включается Flask-WTF."""

from flask_wtf import FlaskForm
from wtforms import (
    BooleanField,
    HiddenField,
    PasswordField,
    SelectField,
    StringField,
    TextAreaField,
)
from wtforms.validators import (
    DataRequired,
    Email,
    Length,
    Optional,
    Regexp,
    ValidationError,
)

TOPIC_CHOICES = [
    ("audit", "AI-аудит процесса"),
    ("mvp", "MVP / прототип"),
    ("integration", "Внедрение и интеграции"),
    ("faq", "FAQ-ассистент / первая линия"),
    ("support", "Поддержка существующего решения"),
    ("other", "Другое"),
]


class InquiryForm(FlaskForm):
    name = StringField(
        "Имя",
        validators=[DataRequired(message="Укажите имя."), Length(min=2, max=120)],
    )
    email = StringField(
        "Email",
        validators=[
            DataRequired(message="Укажите email — на него можно ответить."),
            Email(message="Проверьте формат email."),
            Length(max=255),
        ],
    )
    phone = StringField(
        "Телефон",
        validators=[
            DataRequired(message="Укажите телефон."),
            Length(min=6, max=40),
            Regexp(
                r"^[\d\s\+\-\(\)]{6,40}$",
                message="Телефон: цифры, пробел, +, скобки или дефис.",
            ),
        ],
    )
    company = StringField("Компания", validators=[Optional(), Length(max=160)])
    topic = SelectField(
        "Тема сообщения",
        choices=TOPIC_CHOICES,
        validators=[DataRequired(message="Выберите тему.")],
    )
    message = TextAreaField(
        "Описание задачи",
        validators=[
            DataRequired(message="Кратко опишите задачу."),
            Length(min=10, max=4000, message="Текст: от 10 до 4000 символов."),
        ],
    )
    consent = BooleanField(
        "Согласен на обработку персональных данных",
        validators=[DataRequired(message="Нужно согласие на обработку данных.")],
    )
    # Скрытое поле-ловушка: боты его заполняют, люди — нет.
    website = HiddenField("website")

    def validate_website(self, field):
        if field.data:
            raise ValidationError("Заявка отклонена.")


class LoginForm(FlaskForm):
    username = StringField(
        "Логин",
        validators=[DataRequired(message="Введите логин."), Length(max=64)],
    )
    password = PasswordField(
        "Пароль",
        validators=[DataRequired(message="Введите пароль.")],
    )
