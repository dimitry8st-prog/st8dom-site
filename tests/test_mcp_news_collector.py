import pytest
import requests
import xml.etree.ElementTree as ET

from scripts import collect_portal_news as collector


RSS = b"""<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel>
  <item>
    <title>MCP release update</title>
    <link>https://blog.modelcontextprotocol.io/posts/release-update/</link>
    <description>&lt;p&gt;Official protocol changes and migration notes.&lt;/p&gt;</description>
    <pubDate>Mon, 23 Nov 2026 09:00:00 +0000</pubDate>
  </item>
  <item>
    <title>Duplicate</title>
    <link>https://blog.modelcontextprotocol.io/posts/release-update/</link>
  </item>
  <item>
    <title>External</title>
    <link>https://example.org/posts/not-official/</link>
  </item>
</channel></rss>"""


def response(url, status=200, body=RSS, content_type="application/xml"):
    result = requests.Response()
    result.status_code = status
    result.url = url
    result.headers["Content-Type"] = content_type
    result._content = body
    result._content_consumed = True
    return result


def test_parse_mcp_feed_deduplicates_and_restricts_links():
    assert collector.parse_mcp_feed(RSS) == [{
        "title": "MCP release update",
        "source_url": "https://blog.modelcontextprotocol.io/posts/release-update/",
        "summary": "Official protocol changes and migration notes.",
        "stream": "science-ai",
        "evidence": "Официальный источник; ручная проверка",
        "published_date": "Mon, 23 Nov 2026 09:00:00 +0000",
    }]


@pytest.mark.parametrize("body", [
    b"<html>not RSS</html>",
    b"<rss><channel/></rss>",
    b"x" * (collector.MCP_FEED_LIMIT + 1),
])
def test_parse_mcp_rejects_invalid_or_changed_feed(body):
    with pytest.raises((ValueError, ET.ParseError)) as error:
        collector.parse_mcp_feed(body)
    assert error.value is not None


def test_collect_mcp_saves_private_cards(monkeypatch):
    saved = []
    monkeypatch.setattr(
        collector.requests,
        "get",
        lambda *args, **kwargs: response(collector.MCP_SOURCE.url),
    )
    monkeypatch.setattr(
        collector,
        "save_material",
        lambda **fields: (saved.append(fields), True),
    )

    assert collector.collect_mcp() == {
        "matched": 1,
        "created": 1,
        "existing": 0,
    }
    assert saved[0]["evidence"] == "Официальный источник; ручная проверка"


@pytest.mark.parametrize("url,content_type", [
    ("https://example.org/index.xml", "application/xml"),
    ("https://blog.modelcontextprotocol.io/index.xml", "text/html"),
])
def test_collect_mcp_rejects_redirects_and_non_xml(monkeypatch, url, content_type):
    monkeypatch.setattr(
        collector.requests,
        "get",
        lambda *args, **kwargs: response(url, content_type=content_type),
    )
    with pytest.raises(ValueError):
        collector.collect_mcp()
