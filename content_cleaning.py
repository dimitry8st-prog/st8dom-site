"""Deterministic cleaning gate for untrusted scraped content.

The module deliberately runs before any LLM call. It normalizes URLs and text,
flags instruction-like fragments, and produces stable hashes for deduplication.
"""

from __future__ import annotations

import hashlib
import html
import re
import unicodedata
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


TRACKING_KEYS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "source",
    "yclid",
}
PROMPT_INJECTION_MARKERS = (
    "ignore previous instructions",
    "ignore all previous instructions",
    "system prompt",
    "developer message",
    "reveal your instructions",
    "игнорируй предыдущие инструкции",
    "игнорируй все инструкции",
    "системный промпт",
    "раскрой свои инструкции",
)


class _VisibleTextParser(HTMLParser):
    block_tags = {
        "article",
        "blockquote",
        "br",
        "div",
        "h1",
        "h2",
        "h3",
        "h4",
        "li",
        "main",
        "p",
        "section",
        "tr",
    }
    ignored_tags = {"script", "style", "noscript", "svg", "template"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._ignored_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in self.ignored_tags:
            self._ignored_depth += 1
        elif not self._ignored_depth and tag in self.block_tags:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.ignored_tags and self._ignored_depth:
            self._ignored_depth -= 1
        elif not self._ignored_depth and tag in self.block_tags:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth:
            self.parts.append(data)


def normalize_url(value: str) -> str:
    """Return a canonical public HTTP(S) URL without tracking parameters."""
    if not isinstance(value, str):
        raise ValueError("URL must be a string.")
    parsed = urlsplit(value.strip())
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Only complete HTTP(S) URLs are accepted.")

    scheme = parsed.scheme.lower()
    host = parsed.hostname.lower().rstrip(".")
    port = parsed.port
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        host = f"{host}:{port}"

    query = []
    for key, item in parse_qsl(parsed.query, keep_blank_values=True):
        lowered = key.casefold()
        if lowered.startswith("utm_") or lowered in TRACKING_KEYS:
            continue
        query.append((key, item))
    query.sort()

    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    if path != "/":
        path = path.rstrip("/")
    return urlunsplit((scheme, host, path, urlencode(query, doseq=True), ""))


def html_to_text(value: str, *, limit: int = 50_000) -> str:
    """Extract visible text, normalize Unicode, and keep paragraph boundaries."""
    if not isinstance(value, str):
        return ""
    parser = _VisibleTextParser()
    parser.feed(value)
    parser.close()
    text = html.unescape("".join(parser.parts))
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[\u200b-\u200f\u202a-\u202e\u2060\ufeff]", "", text)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    paragraphs = [line for line in lines if line]
    return "\n\n".join(paragraphs)[:limit].strip()


def detect_prompt_injection(text: str) -> list[str]:
    lowered = text.casefold()
    return [marker for marker in PROMPT_INJECTION_MARKERS if marker in lowered]


def _domain_allowed(hostname: str, allowed_domains: set[str] | None) -> bool:
    if not allowed_domains:
        return True
    return any(hostname == domain or hostname.endswith(f".{domain}") for domain in allowed_domains)


def clean_scraped_item(
    item: dict,
    *,
    allowed_domains: set[str] | None = None,
    minimum_text_length: int = 200,
) -> dict:
    """Clean one raw record and classify it as candidate, quarantine, or reject."""
    if not isinstance(item, dict):
        raise ValueError("Scraped item must be an object.")

    rejection_reasons: list[str] = []
    try:
        canonical_url = normalize_url(str(item.get("url", "")))
    except ValueError:
        canonical_url = ""
        rejection_reasons.append("invalid_url")

    hostname = urlsplit(canonical_url).hostname or ""
    normalized_allowlist = {domain.casefold().lstrip(".") for domain in (allowed_domains or set())}
    if canonical_url and not _domain_allowed(hostname, normalized_allowlist):
        rejection_reasons.append("domain_not_allowed")

    title = html_to_text(str(item.get("title", "")), limit=220)
    if not title:
        rejection_reasons.append("missing_title")

    raw_text = next(
        (
            value
            for key in ("transcript", "content", "text", "description")
            if isinstance((value := item.get(key)), str) and value.strip()
        ),
        "",
    )
    clean_text = html_to_text(raw_text)
    if len(clean_text) < minimum_text_length:
        rejection_reasons.append("content_too_short")

    injection_markers = detect_prompt_injection(clean_text)
    content_hash = hashlib.sha256(clean_text.encode("utf-8")).hexdigest()
    url_hash = hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()
    status = "reject" if rejection_reasons else "quarantine" if injection_markers else "candidate"

    return {
        "status": status,
        "title": title,
        "canonical_url": canonical_url,
        "source_domain": hostname,
        "published_at": item.get("published_at") or item.get("date"),
        "clean_text": clean_text,
        "content_hash": content_hash,
        "url_hash": url_hash,
        "prompt_injection_markers": injection_markers,
        "rejection_reasons": rejection_reasons,
    }


def deduplicate_items(items: list[dict]) -> tuple[list[dict], list[dict]]:
    """Keep the first unique URL/content pair and return duplicate records separately."""
    unique: list[dict] = []
    duplicates: list[dict] = []
    seen_urls: set[str] = set()
    seen_content: set[str] = set()
    for item in items:
        url_hash = item.get("url_hash")
        content_hash = item.get("content_hash")
        if (url_hash and url_hash in seen_urls) or (content_hash and content_hash in seen_content):
            duplicates.append(item)
            continue
        if url_hash:
            seen_urls.add(url_hash)
        if content_hash:
            seen_content.add(content_hash)
        unique.append(item)
    return unique, duplicates
