"""Проверка автоответа и лимитов, без отправки реальных писем."""

from datetime import datetime, timezone
from unittest.mock import patch
from uuid import uuid4

from app import app
from extensions import db
from inquiry_autoreply import is_price_question, send_price_auto_reply
from models import Inquiry, InquiryAutoReply


def _configure(monkeypatch):
    monkeypatch.setitem(app.config, "INQUIRY_AUTO_REPLY_ENABLED", True)
    monkeypatch.setitem(app.config, "SMTP_USERNAME", "sender@gmail.com")
    monkeypatch.setitem(app.config, "SMTP_PASSWORD", "app-password")
    monkeypatch.setitem(app.config, "SMTP_FROM", "sender@gmail.com")
    monkeypatch.setitem(app.config, "SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setitem(app.config, "SMTP_PORT", 587)
    monkeypatch.setitem(app.config, "SMTP_USE_TLS", True)


def _inquiry(email, number, message="Здравствуйте, какая у вас стоимость услуги?"):
    return Inquiry(id=number, name="Посетитель", email=email, topic="support", message=message)


def test_price_question_selection_is_narrow():
    assert is_price_question("Здравствуйте, какая у вас цена?")
    assert is_price_question("Hi, I wanted to know your price.")
    assert is_price_question("Sveiki, aš norėjau sužinoti jūsų kainą.")
    assert not is_price_question("Нужна автоматизация отдела продаж")
    assert not is_price_question("Our backlinks price: https://example.com")


def test_auto_reply_requires_request_and_sends_only_once_per_week(monkeypatch):
    _configure(monkeypatch)
    inquiry_id = 9000000
    email = f"visitor-{uuid4().hex}@example.com"
    try:
        with app.app_context(), patch("inquiry_autoreply.smtplib.SMTP") as smtp_class:
            smtp = smtp_class.return_value.__enter__.return_value
            inquiry = _inquiry(email, inquiry_id)
            assert send_price_auto_reply(inquiry, app, requested=False) is False
            assert send_price_auto_reply(inquiry, app, requested=True) is True
            assert send_price_auto_reply(inquiry, app, requested=True) is False
            smtp.send_message.assert_called_once()
            mail = smtp.send_message.call_args.args[0]
            assert mail["To"] == email
            assert "Уточните" in mail.get_content()
            assert inquiry.message not in mail.get_content()
            assert InquiryAutoReply.query.filter_by(inquiry_id=inquiry_id, sent=True).count() == 1
    finally:
        with app.app_context():
            InquiryAutoReply.query.filter_by(inquiry_id=inquiry_id).delete()
            db.session.commit()


def test_auto_reply_skips_promotion_and_missing_smtp(monkeypatch):
    _configure(monkeypatch)
    with app.app_context(), patch("inquiry_autoreply.smtplib.SMTP") as smtp_class:
        email = f"visitor-{uuid4().hex}@example.com"
        assert send_price_auto_reply(
            _inquiry(email, 9000001, "Цена backlinks: https://example.com"),
            app, requested=True,
        ) is False
        monkeypatch.setitem(app.config, "SMTP_PASSWORD", "")
        assert send_price_auto_reply(
            _inquiry(email, 9000001), app, requested=True
        ) is False
        smtp_class.assert_not_called()


def test_auto_reply_global_daily_limit(monkeypatch):
    _configure(monkeypatch)
    test_id = 9000002
    records = [
        InquiryAutoReply(
            recipient_key=uuid4().hex, inquiry_id=test_id,
            attempted_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        for _ in range(20)
    ]
    try:
        with app.app_context(), patch("inquiry_autoreply.smtplib.SMTP") as smtp_class:
            db.session.add_all(records)
            db.session.commit()
            assert send_price_auto_reply(
                _inquiry(f"visitor-{uuid4().hex}@example.com", 9000003),
                app, requested=True,
            ) is False
            smtp_class.assert_not_called()
    finally:
        with app.app_context():
            InquiryAutoReply.query.filter_by(inquiry_id=test_id).delete()
            db.session.commit()


def test_smtp_failure_never_triggers_repeated_automatic_send(monkeypatch):
    _configure(monkeypatch)
    test_id = 9000004
    inquiry = _inquiry(f"visitor-{uuid4().hex}@example.com", test_id)
    try:
        with app.app_context(), patch("inquiry_autoreply.smtplib.SMTP", side_effect=OSError("offline")) as smtp:
            assert send_price_auto_reply(inquiry, app, requested=True) is False
            assert send_price_auto_reply(inquiry, app, requested=True) is False
            assert smtp.call_count == 1
            assert InquiryAutoReply.query.filter_by(inquiry_id=test_id, sent=False).count() == 1
    finally:
        with app.app_context():
            InquiryAutoReply.query.filter_by(inquiry_id=test_id).delete()
            db.session.commit()


def test_contact_form_passes_explicit_reply_request(client, monkeypatch):
    email = f"visitor-{uuid4().hex}@example.com"
    called = []
    monkeypatch.setattr("app.notify_email", lambda inquiry, site: False)
    monkeypatch.setattr("app.notify_telegram", lambda inquiry, site: None)
    monkeypatch.setattr(
        "app.send_price_auto_reply",
        lambda inquiry, site, *, requested: called.append((inquiry.email, requested)),
    )
    try:
        response = client.post(
            "/contact/",
            data={
                "name": "Иван", "email": email, "phone": "+7 900 000-00-00",
                "topic": "audit", "message": "Сколько стоит аудит процесса?",
                "consent": "y", "reply_requested": "y",
            },
        )
        assert response.status_code == 302
        assert called == [(email, True)]
    finally:
        with app.app_context():
            Inquiry.query.filter_by(email=email).delete()
            db.session.commit()
