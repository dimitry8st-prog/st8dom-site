"""Общие расширения Flask, чтобы избежать циклических импортов."""

from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()

login_manager.login_view = "admin_login"
login_manager.login_message = "Войдите, чтобы открыть панель заявок."
login_manager.login_message_category = "info"
