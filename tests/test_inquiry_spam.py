"""Форма не плодит заявки, админ может убрать спам и вернуть ошибочно отмеченное."""

from uuid import uuid4

from app import app
from extensions import db
from models import AdminUser, Inquiry, InquirySpam


def _post(client, email, message, ip):
    return client.post(
        "/contact/",
        data={
            "name": "Тестовый посетитель",
            "email": email,
            "phone": "+7 900 000-00-00",
            "topic": "audit",
            "message": message,
            "consent": "y",
        },
        environ_overrides={"REMOTE_ADDR": ip},
    )


def test_contact_limits_duplicates_and_submissions_across_requests(client, monkeypatch):
    monkeypatch.setattr("app.notify_email", lambda inquiry, site: False)
    monkeypatch.setattr("app.notify_telegram", lambda inquiry, site: None)
    token = uuid4().hex
    email = f"spam-test-{token}@example.com"
    ip = "198.51.100.42"
    try:
        first = _post(client, email, f"Нужен аудит {token} и план внедрения", ip)
        assert first.status_code == 302
        duplicate = _post(client, email, f"  нужен   АУДИТ {token} и план внедрения  ", ip)
        assert duplicate.status_code == 409
        assert "уже получена".encode() in duplicate.data
        for index in (2, 3):
            assert _post(client, email, f"Другая задача {token} номер {index}", ip).status_code == 302
        limited = _post(client, email, f"Другая задача {token} номер 4", ip)
        assert limited.status_code == 429
        assert limited.headers["Retry-After"] == "3600"
        with app.app_context():
            assert Inquiry.query.filter_by(email=email).count() == 3
    finally:
        with app.app_context():
            Inquiry.query.filter_by(email=email).delete()
            db.session.commit()


def test_admin_marks_spam_and_restores_without_deleting(client):
    token = uuid4().hex
    with app.app_context():
        item = Inquiry(
            name=f"Заявка {token}", email=f"admin-test-{token}@example.com",
            topic="audit", message="Проверка кнопок в админке", ip_hash=token,
        )
        db.session.add(item)
        db.session.commit()
        item_id = item.id
        admin_id = AdminUser.query.first().id
    try:
        assert client.post(f"/admin/inquiries/{item_id}/spam/").status_code == 302
        with client.session_transaction() as session:
            session["_user_id"] = str(admin_id)
            session["_fresh"] = True
        assert token.encode() in client.get("/admin/?status=all").data
        assert client.post(f"/admin/inquiries/{item_id}/spam/?status=all").status_code == 302
        assert token.encode() not in client.get("/admin/?status=all").data
        spam_page = client.get("/admin/?status=spam")
        assert token.encode() in spam_page.data
        assert "Восстановить".encode() in spam_page.data
        with app.app_context():
            assert db.session.get(InquirySpam, item_id) is not None
            assert db.session.get(Inquiry, item_id).is_read is True
        assert client.post(f"/admin/inquiries/{item_id}/restore/?status=spam").status_code == 302
        assert token.encode() in client.get("/admin/?status=all").data
        with app.app_context():
            assert db.session.get(InquirySpam, item_id) is None
        # Существующая кнопка удаления удаляет и связанную пометку.
        client.post(f"/admin/inquiries/{item_id}/spam/")
        assert client.post(f"/admin/inquiries/{item_id}/delete/?status=spam").status_code == 302
        with app.app_context():
            assert db.session.get(Inquiry, item_id) is None
            assert db.session.get(InquirySpam, item_id) is None
    finally:
        with app.app_context():
            item = db.session.get(Inquiry, item_id)
            if item:
                db.session.delete(item)
                db.session.commit()
