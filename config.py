"""Конфигурация приложения. Секреты читаются только из окружения."""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


class Config:
    """Базовые настройки Flask. Не храните ключи в репозитории."""

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-change-me-in-production")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        f"sqlite:///{BASE_DIR / 'instance' / 'site.db'}",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = 3600

    # Администратор создаётся при первом запуске, если пользователя ещё нет.
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "change-me-now")

    # Публичный канонический URL — для SEO, sitemap и Open Graph.
    SITE_URL = os.environ.get("SITE_URL", "https://st8dom.ru").rstrip("/")

    # Опциональная отправка заявок в Telegram. Без токена форма только пишет в БД.
    TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

    # Email-доставка заявок. Пароль приложения и другие секреты — только в окружении.
    INQUIRY_EMAIL = os.environ.get("INQUIRY_EMAIL", "dimitry8st@gmail.com")
    SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
    SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
    SMTP_FROM = os.environ.get("SMTP_FROM", SMTP_USERNAME)
    SMTP_USE_TLS = os.environ.get("SMTP_USE_TLS", "1").strip().lower() not in {
        "0", "false", "off", "no"
    }

    # Опциональная аналитика. Пустое значение = скрипт-заглушка без внешних вызовов.
    ANALYTICS_ID = os.environ.get("ANALYTICS_ID", "")

    # Виджет FAQ. Без ключа модели отвечает текстом из data/faqs.json.
    CHAT_ENABLED = os.environ.get("CHAT_ENABLED", "1").strip().lower() not in {
        "0",
        "false",
        "off",
        "no",
    }
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
    CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY", "")
    LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "openai").strip().lower()
    OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5-20251001")

    LOG_FILE = os.environ.get("LOG_FILE", str(BASE_DIR / "logs" / "app.log"))
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False
    # В продакшене SECRET_KEY обязан быть задан явно.
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"


def get_config():
    env = os.environ.get("FLASK_ENV", "development").lower()
    if env == "production":
        return ProductionConfig
    return DevelopmentConfig
