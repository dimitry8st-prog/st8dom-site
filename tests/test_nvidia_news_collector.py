import xml.etree.ElementTree as ET

import pytest
import requests

from scripts import collect_portal_news as collector


RSS = b'''<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel>
  <item>
    <title>NVIDIA launches new AI agents</title>
    <link>https://blogs.nvidia.com/blog/new-ai-agents/</link>
    <description>&lt;p&gt;New tools for accelerated computing.&lt;/p&gt;</description>
    <pubDate>Mon, 23 Nov 2026 17:00:00 +0000</pubDate>
  </item>
  <item>
    <title>Gaming promotion</title>
    <link>https://blogs.nvidia.com/blog/gaming-promotion/</link>
    <description>Membership discount.</description>
  </item>
  <item>
    <title>External AI post</title>
    <link>https://example.org/blog/ai/</link>
    <description>Artificial intelligence.</description>
  </item>
</channel></rss>'''


def response(url, body=RSS, content_type="application/rss+xml; charset=UTF-8"):
    result = requests.Response()
    result.status_code = 200
    result.url = url
    result.headers["Content-Type"] = content_type
    result._content = body
    result._content_consumed = True
    return result


def test_parse_nvidia_feed_keeps_only_official_ai_posts():
    assert collector.parse_nvidia_feed(RSS) == [{
        "title": "NVIDIA launches new AI agents",
        "source_url": "https://blogs.nvidia.com/blog/new-ai-agents/",
        "summary": "New tools for accelerated computing.",
        "stream": "science-ai",
        "evidence": "Официальный источник; ручная проверка",
        "published_date": "Mon, 23 Nov 2026 17:00:00 +0000",
    }]


@pytest.mark.parametrize("body", [
    b"<html>not RSS</html>",
    b"<rss><channel/></rss>",
    b"x" * (collector.NVIDIA_FEED_LIMIT + 1),
])
def test_parse_nvidia_rejects_invalid_or_changed_feed(body):
    with pytest.raises((ValueError, ET.ParseError)):
        collector.parse_nvidia_feed(body)


def test_collect_nvidia_saves_private_cards(monkeypatch):
    saved = []
    monkeypatch.setattr(
        collector.requests,
        "get",
        lambda *args, **kwargs: response(collector.NVIDIA_SOURCE.url),
    )
    monkeypatch.setattr(
        collector,
        "save_material",
        lambda **fields: (saved.append(fields), True),
    )

    assert collector.collect_nvidia() == {
        "matched": 1,
        "created": 1,
        "existing": 0,
    }
    assert saved[0]["evidence"] == "Официальный источник; ручная проверка"


@pytest.mark.parametrize("url,content_type", [
    ("https://example.org/feed/", "application/rss+xml"),
    ("https://blogs.nvidia.com/feed/", "text/html"),
])
def test_collect_nvidia_rejects_redirects_and_non_xml(monkeypatch, url, content_type):
    monkeypatch.setattr(
        collector.requests,
        "get",
        lambda *args, **kwargs: response(url, content_type=content_type),
    )
    with pytest.raises(ValueError):
        collector.collect_nvidia()
