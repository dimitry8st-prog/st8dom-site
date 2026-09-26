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
    ("express", "Экспресс-разбор"),
    ("audit", "AI-аудит процесса"),
    ("automation", "Автоматизация процесса"),
    ("telegram-bot", "Telegram-бот MVP"),
    ("rag", "RAG по документам"),
    ("assistant", "AI-ассистент с интеграциями"),
    ("faq", "FAQ-ассистент / первая линия"),
    ("mvp", "Другой MVP / прототип"),
    ("integration", "Внедрение и интеграции"),
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
    reply_requested = BooleanField("Получить ответ по email на вопрос о стоимости")
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


SECTION_CHOICES = [
    ("medicine", "Медицина"),
    ("ai", "AI и промпт-инжиниринг"),
    ("longevity", "Долголетие и будущее человека"),
    ("life-os", "Life-OS"),
]

CONTENT_TYPE_CHOICES = [
    ("article", "Статья"),
    ("review", "Обзор"),
    ("recommendation", "Рекомендация"),
    ("analysis", "Разбор"),
    ("patient", "Материал пациенту"),
]

EDITORIAL_STATUS_CHOICES = [
    ("draft", "Черновик"),
    ("review", "На проверке"),
    ("ready", "Готово к публикации"),
    ("archive", "Архив"),
]


class ArticleForm(FlaskForm):
    """Форма вертикального редакционного среза без прямой автопубликации."""

    title = StringField(
        "Заголовок",
        validators=[DataRequired(), Length(min=5, max=220)],
    )
    slug = StringField(
        "Постоянный адрес",
        validators=[
            DataRequired(),
            Length(min=3, max=220),
            Regexp(
                r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
                message="Используйте латинские буквы, цифры и дефисы.",
            ),
        ],
    )
    summary = TextAreaField(
        "Краткое описание",
        validators=[DataRequired(), Length(min=20, max=600)],
    )
    body = TextAreaField(
        "Текст",
        validators=[DataRequired(), Length(min=80, max=50000)],
    )
    section = SelectField(
        "Раздел",
        choices=SECTION_CHOICES,
        validators=[DataRequired()],
    )
    rubric_id = SelectField("Рубрика", coerce=int, validators=[DataRequired()])
    content_type = SelectField(
        "Тип материала",
        choices=CONTENT_TYPE_CHOICES,
        validators=[DataRequired()],
    )
    status = SelectField(
        "Редакционный статус",
        choices=EDITORIAL_STATUS_CHOICES,
        validators=[DataRequired()],
    )
    tags = StringField(
        "Теги через запятую",
        validators=[DataRequired(), Length(max=500)],
    )
    author = StringField(
        "Автор",
        validators=[DataRequired(), Length(max=120)],
        default="Степанов Д.А.",
    )
    medical_reviewer = StringField(
        "Медицинский редактор",
        validators=[Optional(), Length(max=120)],
    )
    reviewed_confirmed = BooleanField("Медицинская проверка выполнена")
    sources = TextAreaField(
        "Источники — по одному в строке: Название | https://...",
        validators=[Optional(), Length(max=10000)],
    )
    disclaimer = TextAreaField(
        "Предупреждение",
        validators=[Optional(), Length(max=2000)],
    )
    revision_note = StringField(
        "Причина обновления",
        validators=[Optional(), Length(max=500)],
    )
    is_featured = BooleanField("Показывать в рекомендуемых")
