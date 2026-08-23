"""Дымовые проверки маршрутов, формы и админки."""

import pytest

from app import app
from models import Inquiry


@pytest.fixture()
def client():
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    with app.test_client() as client:
        yield client


def test_home_ok(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Обсудить задачу".encode("utf-8") in response.data
    assert b"t.me/Dmitryprompt" not in response.data
    assert b"t.me/dimitry8st" in response.data


def test_cases_and_details(client):
    listing = client.get("/cases/")
    assert listing.status_code == 200
    slugs = [
        "legalbot",
        "docpulse",
        "faq-assistant",
        "telegram-bot",
        "online-store-ops",
        "crm-automation",
        "corporate-site",
        "ai-support",
    ]
    for slug in slugs:
        page = client.get(f"/cases/{slug}/")
        assert page.status_code == 200, slug
        assert "Репозиторий".encode("utf-8") in page.data

    legalbot = client.get("/cases/legalbot/")
    assert b"JustBot" in legalbot.data
    assert b"legalbot-demo.mp4" in legalbot.data
    assert "не замена юриста".encode("utf-8") in legalbot.data

    docpulse = client.get("/cases/docpulse/")
    assert b"DocPulse" in docpulse.data
    assert b"docpulse-demo.mp4" in docpulse.data
    assert "не замена врача".encode("utf-8") in docpulse.data

    faq = client.get("/cases/faq-assistant/")
    assert faq.status_code == 200
    assert b"Faq_assistants" in faq.data
    assert "Обсудить внедрение".encode("utf-8") in faq.data
    assert "Текстовая расшифровка ролика".encode("utf-8") in faq.data
    assert b"faq-assistant-poster.webp" in faq.data
    assert b"faq-assistant-ru.vtt" in faq.data
    assert b"faq-assistant-vo.mp3" in faq.data
    assert 'aria-label="Воспроизвести ролик"'.encode("utf-8") in faq.data
    assert b'preload="none"' in faq.data
    assert b"faq-assistant-demo.mp4" not in faq.data
    assert b"autoplay" not in faq.data.lower()


def test_legal_and_seo(client):
    assert client.get("/privacy/").status_code == 200
    assert client.get("/consent/").status_code == 200
    robots = client.get("/robots.txt")
    assert robots.status_code == 200
    assert b"Sitemap" in robots.data
    sitemap = client.get("/sitemap.xml")
    assert sitemap.status_code == 200
    assert b"/cases/faq-assistant/" in sitemap.data
    assert client.get("/no-such-page/").status_code == 404


def test_contact_prefills_faq_topic(client):
    page = client.get("/contact/?topic=faq")
    assert page.status_code == 200
    assert 'value="faq" selected'.encode("utf-8") in page.data or b'value="faq"' in page.data


def test_contact_validation_and_save(client):
    bad = client.post("/contact/", data={"name": "А"}, follow_redirects=True)
    assert bad.status_code == 200

    ok = client.post(
        "/contact/",
        data={
            "name": "Иван Петров",
            "email": "ivan@example.com",
            "phone": "+7 900 000-00-00",
            "topic": "audit",
            "message": "Нужно разобрать процесс поддержки и собрать MVP.",
            "consent": "y",
        },
        follow_redirects=True,
    )
    assert ok.status_code == 200
    assert "Заявка отправлена".encode("utf-8") in ok.data
    with app.app_context():
        saved = Inquiry.query.filter_by(email="ivan@example.com").first()
        assert saved is not None


def test_admin_requires_login(client):
    response = client.get("/admin/", follow_redirects=True)
    assert response.status_code == 200
    assert "Панель заявок".encode("utf-8") in response.data
