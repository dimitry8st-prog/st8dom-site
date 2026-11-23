"""Catch up private Life-OS source cards; never publish articles or messages."""
import json
import re
import xml.etree.ElementTree as ET
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import requests

from lifeos_ingest import validate_mit_batch
from lifeos_workspace import collect_securitylab, save_material
from news_sources import source_by_key

MIT_FEED = source_by_key("mit-news").url
OPENAI_SOURCE = source_by_key("openai-news")
OPENAI_PAGE_LIMIT = 2 * 1024 * 1024
MCP_SOURCE = source_by_key("mcp-blog")
MCP_FEED_LIMIT = 2 * 1024 * 1024
PATTERNS = [
    ("science-longevity", re.compile(r"\b(aging|ageing|longevity|geroscience|senescence|healthspan)\b", re.I)),
    ("science-neuro", re.compile(r"\b(neural|brain|health|medical|medicine|biomedical|neuroscience|neurology)\b", re.I)),
    ("science-ai", re.compile(r"\b(ai|artificial intelligence|machine learning|robot(?:s|ics)?|engineering)\b", re.I)),
]


class OpenAIProductParser(HTMLParser):
    """Extract official product cards without executing page scripts."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "a":
            href = attributes.get("href", "")
            label = attributes.get("aria-label", "")
            if href.startswith("/index/") and " - Product - " in label:
                self.current = {
                    "title": label.rsplit(" - Product - ", 1)[0].strip(),
                    "href": href,
                    "published_date": "",
                }
        elif tag == "time" and self.current is not None:
            self.current["published_date"] = attributes.get("datetime", "")[:10]

    def handle_endtag(self, tag):
        if tag == "a" and self.current is not None:
            self.rows.append(self.current)
            self.current = None


def parse_openai_product_page(data):
    if len(data) > OPENAI_PAGE_LIMIT:
        raise ValueError("OpenAI page exceeds size limit")
    try:
        page = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("OpenAI page is not UTF-8") from exc
    parser = OpenAIProductParser()
    parser.feed(page)
    rows, seen = [], set()
    for item in parser.rows:
        url = urljoin("https://openai.com", item["href"])
        parts = urlsplit(url)
        title = item["title"]
        published_date = item["published_date"]
        if (parts.scheme != "https" or parts.netloc != "openai.com"
                or not parts.path.startswith("/index/") or not title
                or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", published_date)
                or url in seen):
            continue
        seen.add(url)
        rows.append({
            "title": title[:500],
            "source_url": url,
            "summary": "Official OpenAI product announcement; manual review required.",
            "stream": OPENAI_SOURCE.stream,
            "evidence": "Официальный источник; ручная проверка",
            "published_date": published_date,
        })
    if not rows:
        raise ValueError("OpenAI product page format changed or returned no cards")
    if len(rows) > 100:
        raise ValueError("OpenAI batch exceeds 100 records")
    return rows


def parse_mit_feed(data):
    if len(data) > 4 * 1024 * 1024:
        raise ValueError("MIT RSS exceeds size limit")
    root = ET.fromstring(data)
    if root.tag != "rss":
        raise ValueError("MIT did not return RSS")
    rows, seen = [], set()
    for item in root.findall("./channel/item"):
        title = item.findtext("title", "").strip()
        url = item.findtext("link", "").strip()
        parts = urlsplit(url)
        if parts.scheme != "https" or parts.netloc != "news.mit.edu" or not title:
            continue
        summary = " ".join(unescape(re.sub(r"<[^>]*>", " ", item.findtext("description", ""))).split())
        stream = next((s for s, pattern in PATTERNS if pattern.search(title + " " + summary)), None)
        if stream and url not in seen:
            seen.add(url)
            rows.append(dict(title=title[:500], source_url=url, summary=summary[:2000],
                             stream=stream, published_date=item.findtext("pubDate", "")[:100]))
    if len(rows) > 100:
        raise ValueError("MIT batch exceeds 100 records")
    return validate_mit_batch({"materials": rows})


def parse_mcp_feed(data):
    if len(data) > MCP_FEED_LIMIT:
        raise ValueError("MCP RSS exceeds size limit")
    root = ET.fromstring(data)
    if root.tag != "rss":
        raise ValueError("MCP source did not return RSS")
    rows, seen = [], set()
    for item in root.findall("./channel/item"):
        title = item.findtext("title", "").strip()
        url = item.findtext("link", "").strip()
        parts = urlsplit(url)
        if (parts.scheme != "https"
                or parts.netloc != "blog.modelcontextprotocol.io"
                or not parts.path.startswith("/posts/")
                or not title or url in seen):
            continue
        seen.add(url)
        description = unescape(re.sub(
            r"<[^>]*>",
            " ",
            item.findtext("description", ""),
        ))
        rows.append({
            "title": title[:500],
            "source_url": url,
            "summary": " ".join(description.split())[:2000],
            "stream": MCP_SOURCE.stream,
            "evidence": "Официальный источник; ручная проверка",
            "published_date": item.findtext("pubDate", "")[:100],
        })
    if not rows:
        raise ValueError("MCP RSS format changed or returned no posts")
    if len(rows) > 100:
        raise ValueError("MCP batch exceeds 100 records")
    return rows


def collect_mit():
    with requests.get(MIT_FEED, timeout=(5, 20), stream=True) as response:
        response.raise_for_status()
        if urlsplit(response.url).netloc != "news.mit.edu":
            raise ValueError("MIT feed redirected outside official source")
        data = bytearray()
        for chunk in response.iter_content(65536):
            data.extend(chunk)
            if len(data) > 4 * 1024 * 1024:
                raise ValueError("MIT RSS exceeds size limit")
    rows = parse_mit_feed(bytes(data))
    created = sum(save_material(**row)[1] for row in rows)
    return {"matched": len(rows), "created": created, "existing": len(rows) - created}


def collect_openai():
    with requests.get(
        OPENAI_SOURCE.url,
        headers={"User-Agent": "st8dom-source-monitor/1.0"},
        timeout=(5, 20),
        stream=True,
    ) as response:
        response.raise_for_status()
        parts = urlsplit(response.url)
        if parts.scheme != "https" or parts.netloc != "openai.com":
            raise ValueError("OpenAI page redirected outside official source")
        if "text/html" not in response.headers.get("Content-Type", "").lower():
            raise ValueError("OpenAI source did not return HTML")
        data = bytearray()
        for chunk in response.iter_content(65536):
            data.extend(chunk)
            if len(data) > OPENAI_PAGE_LIMIT:
                raise ValueError("OpenAI page exceeds size limit")
    rows = parse_openai_product_page(bytes(data))
    created = sum(save_material(**row)[1] for row in rows)
    return {"matched": len(rows), "created": created, "existing": len(rows) - created}


def collect_mcp():
    with requests.get(
        MCP_SOURCE.url,
        headers={"User-Agent": "st8dom-source-monitor/1.0"},
        timeout=(10, 30),
        stream=True,
    ) as response:
        response.raise_for_status()
        parts = urlsplit(response.url)
        if parts.scheme != "https" or parts.netloc != "blog.modelcontextprotocol.io":
            raise ValueError("MCP feed redirected outside official source")
        content_type = response.headers.get("Content-Type", "").lower()
        if "xml" not in content_type:
            raise ValueError("MCP source did not return XML")
        data = bytearray()
        for chunk in response.iter_content(65536):
            data.extend(chunk)
            if len(data) > MCP_FEED_LIMIT:
                raise ValueError("MCP RSS exceeds size limit")
    rows = parse_mcp_feed(bytes(data))
    created = sum(save_material(**row)[1] for row in rows)
    return {"matched": len(rows), "created": created, "existing": len(rows) - created}


def main():
    from app import app
    errors = []
    with app.app_context():
        warnings = []
        created, failures = collect_securitylab(warnings=warnings)
        print(json.dumps({"source": "SecurityLab", "created": created, "errors": failures, "warnings": warnings}))
        for warning in warnings:
            print(f"::warning title=SecurityLab RSS::{warning}")
        errors.extend(failures)
        try:
            print(json.dumps({"source": "MIT", **collect_mit()}))
        except (requests.RequestException, ET.ParseError, ValueError) as exc:
            errors.append("MIT: " + type(exc).__name__)
        try:
            print(json.dumps({"source": "OpenAI", **collect_openai()}))
        except (requests.RequestException, ValueError) as exc:
            warning = "OpenAI: " + type(exc).__name__
            print(f"::warning title=OpenAI official source::{warning}")
        try:
            print(json.dumps({"source": "MCP", **collect_mcp()}))
        except (requests.RequestException, ET.ParseError, ValueError) as exc:
            warning = "MCP: " + type(exc).__name__
            print(f"::warning title=MCP official source::{warning}")
        if errors:
            raise SystemExit("News collection incomplete: " + ", ".join(errors))


if __name__ == "__main__":
    main()
