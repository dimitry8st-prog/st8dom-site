from app import app
from models import Article, ImportPackage


def test_gemini_agent_article_is_public_in_agent_technologies(client):
    slug = "gemini-agent-tsifrovoy-sotrudnik-google"

    detail = client.get(f"/materials/{slug}/")
    assert detail.status_code == 200
    assert "Gemini Agent: Google превращает AI".encode("utf-8") in detail.data
    assert "Инновации в AI".encode("utf-8") not in detail.data
    assert "Агентные технологии".encode("utf-8") in detail.data

    listing = client.get(
        "/materials/?section=ai&rubric=innovations-agents&type=analysis"
    )
    assert listing.status_code == 200
    assert slug.encode() in listing.data

    search = client.get("/search/?q=Gemini+Agent")
    assert search.status_code == 200
    assert slug.encode() in search.data

    sitemap = client.get("/sitemap.xml")
    assert f"/materials/{slug}/".encode() in sitemap.data

    with app.app_context():
        article = Article.query.filter_by(slug=slug).one()
        record = ImportPackage.query.filter_by(
            package_id="dis-google-gemini-agent-2026-10"
        ).one()
        assert article.status == "published"
        assert article.section == "ai"
        assert article.rubric.slug == "innovations-agents"
        assert article.author == "Степанов Д.А."
        assert len(article.sources) == 4
        assert record.status == "published"
