from app import app
from models import Article


def test_gemini_tool_retrieval_news_is_public_and_sourced(client):
    slug = "gemini-tool-retrieval-ii-agenty-2026"
    page = client.get(f"/materials/{slug}/")
    assert page.status_code == 200
    assert b"gemini-api-tool-retrieval/" in page.data
    assert slug.encode() in client.get("/materials/?section=ai").data
    with app.app_context():
        article = Article.query.filter_by(slug=slug).one()
        assert article.is_public
        assert article.rubric.slug == "innovations-agents"
        assert len(article.sources) == 4
