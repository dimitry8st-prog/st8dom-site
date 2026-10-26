"""Offline tests for the AAIF weekly source collector and AI section."""
from pathlib import Path

import pytest

from scripts.aaif_weekly_scan import (
    extract_article,
    normalized_date,
    official_link,
    scan,
    load_snapshot,
)


class StubResponse:
    def __init__(self, url, html):
        self.url = url
        self.content = html.encode("utf-8")
        self.text = html

    def raise_for_status(self):
        return None


class StubSession:
    def __init__(self, pages):
        self.pages = pages

    def get(self, url, **kwargs):
        if url not in self.pages:
            raise ValueError("Not in test fixture")
        return StubResponse(url, self.pages[url])


def test_first_party_only_and_tracking_removed():
    assert official_link("/blog/agent-skills?utm_source=x#top", "https://aaif.io/") == "https://aaif.io/blog/agent-skills"
    assert official_link("https://evil.example/news/agent", "https://aaif.io/") is None
    assert official_link("//evil.example/blog/agent", "https://aaif.io/") is None
    assert official_link("http://aaif.io/blog/agent", "https://aaif.io/") is None
    assert official_link("/news", "https://aaif.io/") is None


def test_article_metadata_and_date():
    html = ('<html><head><meta name="description" content="Four new projects"></head>'
            '<body><h1>Agentic AI Foundation Adds New Projects</h1>'
            '<time datetime="2026-10-22T12:00:00Z"></time></body></html>')
    row = extract_article("https://aaif.io/news/four-projects", html)
    assert row["title"] == "Agentic AI Foundation Adds New Projects"
    assert row["published_date"] == "2026-10-22"
    assert row["review_status"] == "pending"


def test_scan_keeps_existing_items_and_deduplicates():
    news = "https://aaif.io/news/four-projects"
    pages = {
        "https://aaif.io/": '<a href="/news/four-projects">Four projects</a>',
        "https://aaif.io/blog": '<a href="/news/four-projects?tracking=1">Same link</a>',
        "https://aaif.io/news": '<a href="https://evil.test/news/other">External</a>',
        news: ('<h1>AAIF Accepts Four New Open Projects</h1>'
               '<meta property="article:published_time" content="2026-10-22">'
               '<meta name="description" content="Agent Skills and more">'),
    }
    previous = {"items": []}
    snapshot, count = scan(StubSession(pages), previous)
    assert count == 1
    assert len(snapshot["items"]) == 1
    assert snapshot["items"][0]["url"] == news
    assert snapshot["items"][0]["published_date"] == "2026-10-22"
    second, second_count = scan(StubSession(pages), snapshot)
    assert second_count == 0
    assert second == snapshot


def test_network_error_keeps_previous_snapshot():
    with pytest.raises(RuntimeError):
        scan(StubSession({}), {"items": [{"title": "Existing", "url": "https://aaif.io/news/stable"}]})


def test_ai_page_shows_official_aaif_links(client):
    response = client.get("/directions/ai/")
    assert response.status_code == 200
    assert "Еженедельный мониторинг AAIF".encode("utf-8") in response.data
    assert b"aaif.io/news/agentic-ai-foundation-announces-four-new-projects" in response.data
    assert "На проверке".encode("utf-8") in response.data
