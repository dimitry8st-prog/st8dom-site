"""Regression: approved Anthropic IPO article is loaded into public catalog."""

from models import Article


SLUG = "anthropic-ipo-83-dollara-81-34-mlrd-19-noyabrya-2026"


def test_anthropic_ipo_article_is_published_in_seed(client):
    article = Article.query.filter_by(slug=SLUG).one_or_none()
    assert article is not None, "Editorial seeding did not import the IPO package"
    assert article.is_public, "IPO article exists but is not published"
    assert article.rubric.slug == "innovations-research"
    assert article.sources, "IPO article must retain attributable sources"


def test_anthropic_ipo_public_route_returns_200(client):
    response = client.get(f"/materials/{SLUG}/")
    assert response.status_code == 200
    assert "Anthropic".encode() in response.data
