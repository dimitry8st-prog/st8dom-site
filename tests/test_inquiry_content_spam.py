"""Фильтр не отправляет спам и сохраняет возможность восстановления."""

from unittest.mock import Mock
from uuid import uuid4

import pytest

from app import app
from extensions import db
from inquiry_spam import content_spam_reason
from models import Inquiry, InquirySpam


@pytest.mark.parametrize("text", [
    "Γεια σου, ήθελα να μάθω την τιμή σας.",
    "  ΓΕΙΑ ΣΟΥ! ΗΘΕΛΑ ΝΑ ΜΑΘΩ ΤΗΝ ΤΙΜΗ ΣΑΣ; ",
    "Γεια\u200b σου, ήθελα να μάθω την τιμή σας.",
])
def test_confirmed_template_variants(text):
    assert content_spam_reason(text) == "known_price_template"


@pytest.mark.parametrize("text", [
    "Здравствуйте, сколько стоит консультация?",
    "Hi, I wanted to know your price.",
    "Γεια σας, χρειάζομαι έναν ιστότοπο για την κλινική μου.",
    "Γεια σου, ήθελα να μάθω την τιμή σας. Χρειάζομαι Telegram bot.",
    "Примеры для сайта: https://one.example https://two.example https://three.example",
    "Нужна автоматизация SEO promotion и отчётов.",
])
def test_legitimate_messages_are_not_spam(text):
    assert content_spam_reason(text) is None


def test_promotion_needs_both_signals():
    assert content_spam_reason(
        "Buy backlinks https://one.example https://two.example https://three.example"
    ) == "bulk_link_promotion"


def _post(client, email, message):
    return client.post("/contact/", data={
        "name": "Посетитель", "email": email, "phone": "+7 900 000-00-00",
        "company": "google", "topic": "other", "message": message, "consent": "y",
    }, environ_overrides={"REMOTE_ADDR": "198.51.100.83"})


def test_quarantine_skips_all_delivery_and_restoration_unblocks_sender(client, monkeypatch):
    deliveries = [Mock(return_value=False) for _ in range(3)]
    for name, mock in zip(("notify_email", "notify_telegram", "send_price_auto_reply"), deliveries):
        monkeypatch.setattr("app." + name, mock)
    email = f"filter-{uuid4().hex}@example.com"
    try:
        response = _post(client, email, "Γεια σου, ήθελα να μάθω την τιμή σας.")
        assert response.status_code == 302
        with app.app_context():
            item = Inquiry.query.filter_by(email=email).one()
            assert item.spam_flag is not None
            assert item.is_read
        assert all(not mock.called for mock in deliveries)

        assert _post(client, email, "Повторное обращение с другим текстом").status_code == 302
        with app.app_context():
            items = Inquiry.query.filter_by(email=email).all()
            assert len(items) == 2
            assert all(item.spam_flag is not None for item in items)
            for item in items:
                item.spam_flag = None
            db.session.commit()
        assert all(not mock.called for mock in deliveries)

        assert _post(client, email, "Нужен Telegram бот для записи клиентов").status_code == 302
        assert all(mock.call_count == 1 for mock in deliveries)
        with app.app_context():
            assert Inquiry.query.filter_by(email=email).filter(~Inquiry.spam_flag.has()).count() == 3
    finally:
        with app.app_context():
            for item in Inquiry.query.filter_by(email=email).all():
                db.session.delete(item)
            db.session.commit()


def test_greek_project_request_is_delivered(client, monkeypatch):
    email = f"greek-project-{uuid4().hex}@example.com"
    delivery = Mock(return_value=False)
    monkeypatch.setattr("app.notify_email", delivery)
    monkeypatch.setattr("app.notify_telegram", Mock())
    monkeypatch.setattr("app.send_price_auto_reply", Mock())
    try:
        assert _post(client, email, "Γεια σας, χρειάζομαι έναν ιστότοπο για την κλινική μου.").status_code == 302
        delivery.assert_called_once()
        with app.app_context():
            assert Inquiry.query.filter_by(email=email).one().spam_flag is None
    finally:
        with app.app_context():
            for item in Inquiry.query.filter_by(email=email).all():
                db.session.delete(item)
            db.session.commit()
