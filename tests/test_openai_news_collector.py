import pytest
import requests

from scripts import collect_portal_news as collector


PAGE = b"""<!doctype html><html><body>
<a aria-label="Introducing Example Model - Product - Nov 23, 2026"
   href="/index/introducing-example-model/">
  <div>Introducing Example Model</div>
  <time dateTime="2026-11-23T08:00:00.000Z">Nov 23, 2026</time>
</a>
<a aria-label="Duplicate - Product - Nov 23, 2026"
   href="/index/introducing-example-model/">
  <time dateTime="2026-11-23T08:00:00.000Z">Nov 23, 2026</time>
</a>
<a aria-label="External - Product - Nov 23, 2026"
   href="https://example.org/not-official">
  <time dateTime="2026-11-23T08:00:00.000Z">Nov 23, 2026</time>
</a>
</body></html>"""


def response(url, status=200, body=PAGE, content_type="text/html; charset=utf-8"):
    result = requests.Response()
    result.status_code = status
    result.url = url
    result.headers["Content-Type"] = content_type
    result._content = body
    result._content_consumed = True
    return result


def test_parse_openai_cards_deduplicates_and_restricts_links():
    rows = collector.parse_openai_product_page(PAGE)
    assert rows == [{
        "title": "Introducing Example Model",
        "source_url": "https://openai.com/index/introducing-example-model/",
        "summary": "Official OpenAI product announcement; manual review required.",
        "stream": "science-ai",
        "evidence": "Официальный источник; ручная проверка",
        "published_date": "2026-11-23",
    }]


@pytest.mark.parametrize("body", [
    b"<html><body>No product cards</body></html>",
    b"x" * (collector.OPENAI_PAGE_LIMIT + 1),
    b"\xff\xfe",
])
def test_parse_openai_rejects_invalid_or_changed_pages(body):
    with pytest.raises(ValueError):
        collector.parse_openai_product_page(body)


def test_collect_openai_saves_private_cards(monkeypatch):
    saved = []
    monkeypatch.setattr(
        collector.requests,
        "get",
        lambda *args, **kwargs: response(collector.OPENAI_SOURCE.url),
    )
    monkeypatch.setattr(
        collector,
        "save_material",
        lambda **fields: (saved.append(fields), True),
    )

    assert collector.collect_openai() == {
        "matched": 1,
        "created": 1,
        "existing": 0,
    }
    assert saved[0]["evidence"] == "Официальный источник; ручная проверка"


@pytest.mark.parametrize("url,content_type", [
    ("https://example.org/news", "text/html"),
    ("https://openai.com/news/product-releases/", "application/json"),
])
def test_collect_openai_rejects_redirects_and_non_html(monkeypatch, url, content_type):
    monkeypatch.setattr(
        collector.requests,
        "get",
        lambda *args, **kwargs: response(url, content_type=content_type),
    )
    with pytest.raises(ValueError):
        collector.collect_openai()
