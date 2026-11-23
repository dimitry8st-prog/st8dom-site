import pytest
import requests

from scripts import collect_portal_news as collector


PAGE = b'''<!doctype html><html><body>
<li data-listing-row="row-1">
  <a class="hash_title-link" href="/news/example-model"><h3>Introducing Example Model</h3></a>
  <a class="hash_above-link" href="/news/example-model"><p>Official model announcement.</p></a>
  <div class="hash_details-meta"><div>Nov 23, 2026</div></div>
</li>
<li data-listing-row="row-2">
  <a class="hash_title-link" href="https://example.org/news/external"><h3>External</h3></a>
  <div>Nov 22, 2026</div>
</li>
</body></html>'''


def response(url, body=PAGE, content_type="text/html; charset=utf-8"):
    result = requests.Response()
    result.status_code = 200
    result.url = url
    result.headers["Content-Type"] = content_type
    result._content = body
    result._content_consumed = True
    return result


def test_parse_anthropic_cards_restricts_links_and_normalizes_date():
    assert collector.parse_anthropic_news_page(PAGE) == [{
        "title": "Introducing Example Model",
        "source_url": "https://www.anthropic.com/news/example-model",
        "summary": "Official model announcement.",
        "stream": "science-ai",
        "evidence": "Официальный источник; ручная проверка",
        "published_date": "2026-11-23",
    }]


@pytest.mark.parametrize("body", [
    b"<html><body>No newsroom cards</body></html>",
    b"x" * (collector.ANTHROPIC_PAGE_LIMIT + 1),
    b"\xff\xfe",
])
def test_parse_anthropic_rejects_invalid_or_changed_pages(body):
    with pytest.raises(ValueError):
        collector.parse_anthropic_news_page(body)


def test_collect_anthropic_saves_private_cards(monkeypatch):
    saved = []
    monkeypatch.setattr(
        collector.requests,
        "get",
        lambda *args, **kwargs: response(collector.ANTHROPIC_SOURCE.url),
    )
    monkeypatch.setattr(
        collector,
        "save_material",
        lambda **fields: (saved.append(fields), True),
    )

    assert collector.collect_anthropic() == {
        "matched": 1,
        "created": 1,
        "existing": 0,
    }
    assert saved[0]["evidence"] == "Официальный источник; ручная проверка"


@pytest.mark.parametrize("url,content_type", [
    ("https://example.org/news", "text/html"),
    ("https://www.anthropic.com/news", "application/json"),
])
def test_collect_anthropic_rejects_redirects_and_non_html(monkeypatch, url, content_type):
    monkeypatch.setattr(
        collector.requests,
        "get",
        lambda *args, **kwargs: response(url, content_type=content_type),
    )
    with pytest.raises(ValueError):
        collector.collect_anthropic()
