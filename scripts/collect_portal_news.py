"""Catch up private Life-OS source cards; never publish articles or messages."""
import json
import re
import xml.etree.ElementTree as ET
from html import unescape
from urllib.parse import urlsplit

import requests

from lifeos_ingest import validate_mit_batch
from lifeos_workspace import collect_securitylab, save_material

MIT_FEED = "https://news.mit.edu/rss/feed"
PATTERNS = [
    ("science-longevity", re.compile(r"\b(aging|ageing|longevity|geroscience|senescence|healthspan)\b", re.I)),
    ("science-neuro", re.compile(r"\b(neural|brain|health|medical|medicine|biomedical|neuroscience|neurology)\b", re.I)),
    ("science-ai", re.compile(r"\b(ai|artificial intelligence|machine learning|robot(?:s|ics)?|engineering)\b", re.I)),
]


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


def main():
    from app import app
    errors = []
    with app.app_context():
        created, failures = collect_securitylab()
        print(json.dumps({"source": "SecurityLab", "created": created, "errors": failures}))
        errors.extend(failures)
        try:
            print(json.dumps({"source": "MIT", **collect_mit()}))
        except (requests.RequestException, ET.ParseError, ValueError) as exc:
            errors.append("MIT: " + type(exc).__name__)
        if errors:
            raise SystemExit("News collection incomplete: " + ", ".join(errors))


if __name__ == "__main__":
    main()
