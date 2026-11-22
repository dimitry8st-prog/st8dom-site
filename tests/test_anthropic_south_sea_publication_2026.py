"""Regression: Anthropic/South Sea Bubble article is publicly published."""

from app import app
from models import Article

SLUG = "anthropic-prizrak-yuzhnyh-morey-1720-ai-2026"


def test_south_sea_article_is_seeded_with_sources(client):
    with app.app_context():
        article = Article.query.filter_by(slug=SLUG).one_or_none()
        assert article is not None, "Approved content package is not imported"
        assert article.is_public
        assert article.rubric.slug == "innovations-research"
        assert len(article.sources) >= 6
        assert "South Sea Bubble" in article.body
        assert "ANT-2027-01" in article.body
        assert "не является" in article.disclaimer.lower()


def test_south_sea_article_routes_and_sitemap(client):
    detail = client.get(f"/materials/{SLUG}/")
    assert detail.status_code == 200
    assert "Anthropic".encode() in detail.data
    assert "1720".encode() in detail.data
    assert SLUG.encode() in client.get("/materials/").data
    assert f"/materials/{SLUG}/".encode() in client.get("/sitemap.xml").data
