"""Еженедельный сбор официальных AAIF news/blog без автоматической публикации статей.

Usage: python -m scripts.aaif_weekly_scan
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests

BASE_URL = "https://aaif.io/"
LISTINGS = ("https://aaif.io/", "https://aaif.io/blog", "https://aaif.io/news")
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "data" / "ai" / "aaif-watch.json"
DATE_RE = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})(?!\d)")
JSON_DATE_RE = re.compile(r'"datePublished"\s*:\s*"([^"]+)"')
US_DATE_RE = re.compile(r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+([0-3]?\d),?\s+(20\d{2})\b", re.I)


def official_link(href: str, base: str) -> str | None:
    """Only AAIF first-party news and blog article URLs; strip tracking and anchors."""
    if not href or not isinstance(href, str):
        return None
    try:
        url = urlsplit(urljoin(base, href))
    except ValueError:
        return None
    if url.scheme != "https" or url.hostname not in {"aaif.io", "www.aaif.io"}:
        return None
    path = url.path.rstrip("/")
    if not (path.startswith("/blog/") or path.startswith("/news/")):
        return None
    if path.count("/") != 2 or not re.fullmatch(r"/(?:blog|news)/[a-zA-Z0-9][a-zA-Z0-9-]{1,180}", path):
        return None
    return urlunsplit(("https", "aaif.io", path, "", ""))


class ListingParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)


class ArticleParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.metadata: dict[str, str] = {}
        self.h1: list[str] = []
        self.title: list[str] = []
        self.inside_h1 = False
        self.inside_title = False
        self.time_value = ""

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag == "meta":
            key = d.get("property") or d.get("name")
            if key and d.get("content"):
                self.metadata[key.lower()] = d["content"]
        elif tag == "h1":
            self.inside_h1 = True
        elif tag == "title":
            self.inside_title = True
        elif tag == "time":
            self.time_value = d.get("datetime") or self.time_value

    def handle_endtag(self, tag):
        if tag == "h1":
            self.inside_h1 = False
        elif tag == "title":
            self.inside_title = False

    def handle_data(self, data):
        if self.inside_h1:
            self.h1.append(data)
        if self.inside_title:
            self.title.append(data)


def normalized_date(html: str, parser: ArticleParser) -> str:
    raw = (parser.metadata.get("article:published_time")
           or parser.metadata.get("datepublished")
           or parser.time_value
           or "")
    if not raw:
        match = JSON_DATE_RE.search(html)
        raw = match.group(1) if match else ""
    if not raw:
        match = US_DATE_RE.search(html)
        if match:
            try:
                return datetime.strptime(match.group(0).replace(",", ""), "%B %d %Y").date().isoformat()
            except ValueError:
                return ""
    match = DATE_RE.search(raw)
    if not match:
        return ""
    try:
        return datetime.strptime(match.group(0), "%Y-%m-%d").date().isoformat()
    except ValueError:
        return ""


def extract_article(url: str, html: str) -> dict | None:
    parser = ArticleParser()
    parser.feed(html)
    title = " ".join("".join(parser.h1).split()) or parser.metadata.get("og:title", "") or " ".join("".join(parser.title).split())
    title = title.strip()[:220]
    if len(title) < 8:
        return None
    summary = parser.metadata.get("description") or parser.metadata.get("og:description") or ""
    return {
        "title": title,
        "url": url,
        "published_date": normalized_date(html, parser),
        "summary": " ".join(summary.split())[:350],
        "review_status": "pending",
    }


def fetch_html(session, url: str) -> str:
    response = session.get(url, timeout=15, headers={"User-Agent": "DIS-LifeOS-AAIF-Monitor/1.0 (+https://st8dom.ru)"})
    response.raise_for_status()
    if urlsplit(response.url).hostname not in {"aaif.io", "www.aaif.io"} or urlsplit(response.url).scheme != "https":
        raise ValueError("AAIF source redirected to an untrusted domain.")
    if len(response.content) > 2_000_000:
        raise ValueError("AAIF page too large.")
    return response.text


def scan(session, previous: dict, max_pages: int = 50) -> tuple[dict, int]:
    """Discover current article URLs; keep old records and their review metadata."""
    if not isinstance(previous, dict):
        raise ValueError("Previous snapshot must be an object.")
    old = previous.get("items", [])
    if not isinstance(old, list):
        raise ValueError("Previous items must be a list.")
    known = {item["url"]: item for item in old if isinstance(item, dict) and item.get("url")}
    candidates: list[str] = []
    seen: set[str] = set()

    succeeded = 0
    for listing in LISTINGS:
        try:
            html = fetch_html(session, listing)
            succeeded += 1
        except (requests.RequestException, ValueError) as exc:
            print(f"AAIF listing unavailable: {listing}: {exc}")
            continue
        parser = ListingParser()
        parser.feed(html)
        for href in parser.links:
            url = official_link(href, listing)
            if url and url not in seen:
                seen.add(url)
                candidates.append(url)
    if not succeeded:
        raise RuntimeError("All official AAIF listings unavailable; keep existing snapshot unchanged.")

    discovered = 0
    for url in candidates[:max_pages]:
        if url in known:
            continue
        try:
            html = fetch_html(session, url)
            row = extract_article(url, html)
            if row:
                known[url] = row
                discovered += 1
        except (requests.RequestException, ValueError) as exc:
            print(f"AAIF article unavailable: {url}: {exc}")
    result = dict(previous)
    result["source"] = "Agentic AI Foundation"
    result["source_url"] = BASE_URL
    result["section"] = "ai"
    result["items"] = sorted(known.values(), key=lambda row: (row.get("published_date", ""), row["url"]), reverse=True)[:200]
    return result, discovered


def load_snapshot(path: Path = DEFAULT_OUTPUT) -> dict:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else {"items": []}
    except (OSError, ValueError):
        return {"items": []}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    previous = load_snapshot(args.output)
    updated, count = scan(requests.Session(), previous)
    changed = updated != previous
    if changed:
        updated["last_changed_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"AAIF: new={count}; total={len(updated['items'])}; changed={changed}")
    summary_file = __import__("os").environ.get("GITHUB_STEP_SUMMARY")
    if summary_file:
        with open(summary_file, "a", encoding="utf-8") as summary:
            summary.write(f"AAIF weekly: {count} new; {len(updated['items'])} total. Changed: {changed}.\n")


if __name__ == "__main__":
    main()
