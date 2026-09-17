"""Тематическая навигация, поиск и безопасный контур Life-OS."""

import json

from app import app
from extensions import db
from models import AdminUser, Article, ImportPackage, Rubric, Tag


def login_as_admin(client):
    with app.app_context():
        admin_id = str(AdminUser.query.first().id)
    with client.session_transaction() as session:
        session["_user_id"] = admin_id
        session["_fresh"] = True


def cleanup_import(package_id, slug):
    with app.app_context():
        record = ImportPackage.query.filter_by(package_id=package_id).first()
        if record:
            db.session.delete(record)
            db.session.flush()
        article = Article.query.filter_by(slug=slug).first()
        if article:
            db.session.delete(article)
        db.session.commit()


def valid_package(package_id="lifeos-test-001", slug="lifeos-test-draft"):
    return {
        "package_id": package_id,
        "generator_version": "1.0",
        "article": {
            "title": "Черновик из Life-OS для проверки",
            "slug": slug,
            "summary": "Проверяем безопасный импорт материала в редакционный контур.",
            "body": "Это тестовый текст черновика, который не должен публиковаться автоматически. " * 3,
            "section": "medicine",
            "rubric": "neurology-neurosurgery-neurology-diseases",
            "content_type": "article",
            "status": "published",
            "tags": ["Неврология", "Life-OS"],
        },
        "sources": [{"title": "Проверяемый источник", "url": "https://example.org/source"}],
    }


def test_topic_cards_link_to_rubric_pages(client):
    page = client.get("/directions/medicine/")
    assert page.status_code == 200
    assert b"/directions/medicine/neurology-neurosurgery/" in page.data
    assert page.data.count(b'class="topic-card reveal"') == 4

    topic = client.get("/directions/medicine/neurology-neurosurgery/")
    assert topic.status_code == 200
    assert "Выберите направление".encode("utf-8") in topic.data
    assert "Неврология".encode("utf-8") in topic.data
    assert "Нейрохирургия".encode("utf-8") in topic.data
    assert "Заболевания".encode("utf-8") in topic.data
    assert topic.data.count("Диагностика".encode("utf-8")) == 2
    assert topic.data.count("Лечение".encode("utf-8")) == 2
    assert topic.data.count("<strong>Реабилитация</strong>".encode("utf-8")) == 2
    assert b"neurology-neurosurgery-neurology-diseases" in topic.data
    assert b"neurology-neurosurgery-neurosurgery-rehabilitation" in topic.data
    assert client.get("/directions/medicine/not-found/").status_code == 404


def test_telegram_uses_internal_placeholder(client):
    page = client.get("/telegram/")
    assert page.status_code == 200
    assert "Новый Telegram-бот готовится".encode("utf-8") in page.data
    home = client.get("/")
    assert b"t.me/+VNBg4iudNxw2Mzgy" not in home.data


def test_unified_search_finds_material_tags_and_projects(client):
    by_tag = client.get("/search/?q=RAG")
    assert by_tag.status_code == 200
    assert b"kak-vitalis-proveryaet-istochniki" in by_tag.data
    assert b"Vitalis Medical AI" in by_tag.data
    by_project = client.get("/search/?q=AutoSfera")
    assert b"AutoSfera-AI" in by_project.data


def test_lifeos_import_is_draft_and_idempotent(client):
    package_id, slug = "lifeos-test-001", "lifeos-test-draft"
    cleanup_import(package_id, slug)
    login_as_admin(client)
    payload = json.dumps(valid_package(package_id, slug), ensure_ascii=False)
    first = client.post("/admin/imports/life-os/", data={"package": payload}, follow_redirects=True)
    assert first.status_code == 200
    assert "Создан только черновик".encode("utf-8") in first.data
    with app.app_context():
        article = Article.query.filter_by(slug=slug).one()
        assert article.status == "draft"
        assert ImportPackage.query.filter_by(package_id=package_id).count() == 1
        assert Article.query.filter_by(slug=slug).count() == 1
    assert client.get(f"/materials/{slug}/").status_code == 404

    second = client.post("/admin/imports/life-os/", data={"package": payload}, follow_redirects=True)
    assert second.status_code == 200
    assert "дубликат не создан".encode("utf-8") in second.data
    with app.app_context():
        assert Article.query.filter_by(slug=slug).count() == 1
    cleanup_import(package_id, slug)


def test_lifeos_import_rejects_unsafe_source(client):
    package_id, slug = "lifeos-test-unsafe", "lifeos-test-unsafe"
    cleanup_import(package_id, slug)
    login_as_admin(client)
    payload = valid_package(package_id, slug)
    payload["sources"][0]["url"] = "javascript:alert(1)"
    response = client.post("/admin/imports/life-os/", data={"package": json.dumps(payload)}, follow_redirects=True)
    assert response.status_code == 200
    assert "нужен полный адрес http(s)".encode("utf-8") in response.data
    with app.app_context():
        assert Article.query.filter_by(slug=slug).first() is None
