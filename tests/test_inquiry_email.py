"""Проверки формы и email-доставки заявок."""

from unittest.mock import patch

from app import app, notify_email
from models import Inquiry


def _inquiry():
    return Inquiry(
        id=101,
        name="Посетитель",
        email="visitor@example.com",
        phone="+7 900 000-00-00",
        company="Компания",
        topic="audit",
        message="Нужно разобрать и автоматизировать один рабочий процесс.",
    )


def test_contact_form_does_not_contain_owner_personal_data(client):
    response = client.get("/contact/")
    assert response.status_code == 200
    assert b'autocomplete="off"' in response.data
    assert "Степанов Дмитрий Александрович".encode("utf-8") not in response.data
    assert b"stepanovda@bk.ru" not in response.data
    assert b"+79101389948" not in response.data


def test_notify_email_uses_configured_recipient(monkeypatch):
    monkeypatch.setitem(app.config, "INQUIRY_EMAIL", "dimitry8st@gmail.com")
    monkeypatch.setitem(app.config, "SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setitem(app.config, "SMTP_PORT", 587)
    monkeypatch.setitem(app.config, "SMTP_USERNAME", "sender@gmail.com")
    monkeypatch.setitem(app.config, "SMTP_PASSWORD", "app-password")
    monkeypatch.setitem(app.config, "SMTP_FROM", "sender@gmail.com")
    monkeypatch.setitem(app.config, "SMTP_USE_TLS", True)

    with patch("app.smtplib.SMTP") as smtp_class:
        smtp = smtp_class.return_value.__enter__.return_value
        assert notify_email(_inquiry(), app) is True

    smtp.starttls.assert_called_once()
    smtp.login.assert_called_once_with("sender@gmail.com", "app-password")
    sent = smtp.send_message.call_args.args[0]
    assert sent["To"] == "dimitry8st@gmail.com"
    assert sent["Reply-To"] == "visitor@example.com"


def test_notify_email_keeps_database_fallback_without_credentials(monkeypatch):
    monkeypatch.setitem(app.config, "SMTP_USERNAME", "")
    monkeypatch.setitem(app.config, "SMTP_PASSWORD", "")
    assert notify_email(_inquiry(), app) is False
