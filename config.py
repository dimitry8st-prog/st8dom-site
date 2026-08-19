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

    # Опциональная аналитика. Пустое значение = скрипт-заглушка без внешних вызовов.
    ANALYTICS_ID = os.environ.get("ANALYTICS_ID", "")

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
