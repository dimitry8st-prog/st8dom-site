"""Точка входа для gunicorn и других WSGI-серверов."""

from app import app as application

app = application
