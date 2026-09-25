"""Вертикальный срез публикаций: публичность, предпросмотр и медицинский контроль."""

from datetime import datetime, timezone

from app import app
from extensions import db
from models import AdminUser, Article, ArticleSource, Rubric, Tag


def login_as_admin(client):
    with app.app_context():
        admin = AdminUser.query.first()
        admin_id = str(admin.id)
    with client.session_transaction() as session:
        session["_user_id"] = admin_id
        session["_fresh"] = True


def remove_article(slug):
    with app.app_context():
        article = Article.query.filter_by(slug=slug).first()
        if article:
            db.session.delete(article)
            db.session.commit()


def test_seed_material_is_public_and_connected(client):
    slug = "kak-vitalis-proveryaet-istochniki"
    listing = client.get("/materials/")
    assert listing.status_code == 200
    assert "Новые и рекомендуемые материалы".encode("utf-8") in listing.data
    assert slug.encode() in listing.data

    detail = client.get(f"/materials/{slug}/")
    assert detail.status_code == 200
    assert "Проверено".encode("utf-8") in detail.data
    assert "Источники".encode("utf-8") in detail.data
    assert "Следить за темой".encode("utf-8") in detail.data

    home = client.get("/")
    assert slug.encode() in home.data
    vitalis = client.get("/cases/vitalis-medical-ai/")
    assert slug.encode() in vitalis.data
    sitemap = client.get("/sitemap.xml")
    assert f"/materials/{slug}/".encode() in sitemap.data


def test_stroke_rehabilitation_article_is_structured_and_sourced(client):
    slug = "reabilitaciya-posle-ishemicheskogo-insulta"
    page = client.get(f"/materials/{slug}/")

    assert page.status_code == 200
    assert "Периоды ишемического инсульта".encode("utf-8") in page.data
    assert b"<table>" in page.data
    assert b"<ul>" in page.data
    assert b"## " not in page.data

    with app.app_context():
        article = Article.query.filter_by(slug=slug).one()
        assert article.rubric.slug == "neurology-neurosurgery-neurology-rehabilitation"
        assert article.medical_reviewer == "Степанов Д.А."
        assert len(article.sources) == 15


def test_botulinum_orofacial_pain_article_is_published_and_sourced(client):
    slug = "botulinoterapiya-pri-litsevoy-boli"
    page = client.get(f"/materials/{slug}/")

    assert page.status_code == 200
    assert "Ботулинотерапия при лицевой боли".encode("utf-8") in page.data
    assert "Продолжение серии".encode("utf-8") in page.data
    assert "Медицинская проверка: Степанов Д.А.".encode("utf-8") in page.data
    assert b"10.1080/08869634.2026.2669199" in page.data

    listing = client.get("/materials/")
    assert slug.encode() in listing.data
    sitemap = client.get("/sitemap.xml")
    assert f"/materials/{slug}/".encode() in sitemap.data

    with app.app_context():
        article = Article.query.filter_by(slug=slug).one()
        assert article.status == "published"
        assert article.medical_reviewer == "Степанов Д.А."
        assert article.rubric.slug == "neurology-neurosurgery-neurology-treatment"
        assert len(article.sources) == 11


def test_australian_agent_incident_is_public_with_sources(client):
    slug = "kogda-ai-agent-obhodit-zapret-avstraliya-medicare"
    page = client.get(f"/materials/{slug}/")
    assert page.status_code == 200
    assert "Когда AI-агент обходит запрет".encode() in page.data
    assert "не обнаружила доступа к персональным медицинским записям".encode() in page.data
    assert b"abc.net.au" in page.data
    assert slug.encode() in client.get("/materials/").data
    assert f"/materials/{slug}/".encode() in client.get("/sitemap.xml").data

    with app.app_context():
        article = Article.query.filter_by(slug=slug).one()
        assert article.status == "published"
        assert len(article.sources) == 5


def test_post_stroke_cognitive_technology_article_is_published_and_sourced(client):
    slug = "tekhnologii-vosstanovleniya-kognitivnyh-funktsiy-posle-insulta"
    page = client.get(f"/materials/{slug}/")

    assert page.status_code == 200
    assert "Технологии восстановления когнитивных функций после инсульта".encode("utf-8") in page.data
    assert "Продолжение серии".encode("utf-8") in page.data
    assert "Медицинская проверка: Степанов Д.А.".encode("utf-8") in page.data
    assert b"<table>" in page.data
    assert b"10.1186/s13643-026-03076-2" in page.data

    listing = client.get("/materials/")
    assert slug.encode() in listing.data
    search = client.get("/search/?q=%D0%BA%D0%BE%D0%B3%D0%BD%D0%B8%D1%82%D0%B8%D0%B2%D0%BD%D0%B0%D1%8F+%D1%80%D0%B5%D0%B0%D0%B1%D0%B8%D0%BB%D0%B8%D1%82%D0%B0%D1%86%D0%B8%D1%8F")
    assert slug.encode() in search.data
    sitemap = client.get("/sitemap.xml")
    assert f"/materials/{slug}/".encode() in sitemap.data

    with app.app_context():
        article = Article.query.filter_by(slug=slug).one()
        assert article.status == "published"
        assert article.medical_reviewer == "Степанов Д.А."
        assert article.rubric.slug == "neurology-neurosurgery-neurology-rehabilitation"
        assert len(article.sources) == 11


def test_draft_is_private_but_admin_can_preview(client):
    slug = "test-private-draft"
    remove_article(slug)
    with app.app_context():
        rubric = Rubric.query.filter_by(slug="medical-ai").first()
        article = Article(
            title="Закрытый тестовый черновик",
            slug=slug,
            summary="Этот материал нужен только для проверки закрытого предпросмотра.",
            body="Тестовый текст черновика. " * 10,
            section="ai",
            rubric=rubric,
            content_type="article",
            status="draft",
            author="Степанов Д.А.",
        )
        db.session.add(article)
        db.session.commit()
        article_id = article.id

    assert client.get(f"/materials/{slug}/").status_code == 404
    anonymous_preview = client.get(f"/admin/articles/{article_id}/preview/")
    assert anonymous_preview.status_code == 302

    login_as_admin(client)
    preview = client.get(f"/admin/articles/{article_id}/preview/")
    assert preview.status_code == 200
    assert b"noindex,nofollow" in preview.data
    assert "Предпросмотр".encode("utf-8") in preview.data
    remove_article(slug)


def test_medical_publication_requires_review_sources_and_disclaimer(client):
    slug = "test-medical-publication-gate"
    remove_article(slug)
    with app.app_context():
        rubric = Rubric.query.filter_by(slug="medical-ai").first()
        tag = Tag.query.filter_by(slug="медицина").first()
        article = Article(
            title="Проверка медицинского шлюза",
            slug=slug,
            summary="Материал проверяет обязательные условия медицинской публикации.",
            body="Безопасный тестовый текст публикации. " * 10,
            section="medicine",
            rubric=rubric,
            content_type="analysis",
            status="ready",
            author="Степанов Д.А.",
            tags=[tag],
        )
        db.session.add(article)
        db.session.commit()
        article_id = article.id

    login_as_admin(client)
    blocked = client.post(
        f"/admin/articles/{article_id}/publish/", follow_redirects=True
    )
    assert blocked.status_code == 200
    assert "Публикация заблокирована".encode("utf-8") in blocked.data
    assert client.get(f"/materials/{slug}/").status_code == 404

    with app.app_context():
        article = db.session.get(Article, article_id)
        article.medical_reviewer = "Степанов Д.А."
        article.reviewed_at = datetime.now(timezone.utc)
        article.disclaimer = "Информационный материал, не заменяет консультацию врача."
        article.sources.append(
            ArticleSource(title="Тестовый источник", url="https://example.org/source")
        )
        db.session.commit()

    published = client.post(
        f"/admin/articles/{article_id}/publish/", follow_redirects=True
    )
    assert published.status_code == 200
    assert "Материал опубликован".encode("utf-8") in published.data
    assert client.get(f"/materials/{slug}/").status_code == 200
    remove_article(slug)


def test_article_body_is_escaped(client):
    slug = "test-escaped-publication"
    remove_article(slug)
    with app.app_context():
        rubric = Rubric.query.filter_by(slug="medical-ai").first()
        tag = Tag.query.filter_by(slug="ai").first()
        article = Article(
            title="Проверка безопасного отображения",
            slug=slug,
            summary="Проверка того, что HTML из редакционного текста не исполняется.",
            body="<script>alert('x')</script> " + "Тестовый текст. " * 10,
            section="ai",
            rubric=rubric,
            content_type="article",
            status="published",
            author="Степанов Д.А.",
            published_at=datetime.now(timezone.utc),
            tags=[tag],
        )
        db.session.add(article)
        db.session.commit()

    page = client.get(f"/materials/{slug}/")
    assert page.status_code == 200
    assert b"<script>alert" not in page.data
    assert b"&lt;script&gt;" in page.data
    remove_article(slug)
