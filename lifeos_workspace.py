"""Хранилище Life-OS и сбор официальных RSS SecurityLab."""
import logging
import re
import time
import xml.etree.ElementTree as ET
from html import unescape
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

import requests
from sqlalchemy.exc import IntegrityError

from extensions import db
from models import LifeOSMaterial

STREAMS = {
    "time": {"title": "Время, реальность и прогнозирование", "description": "Квантовая физика, относительность, время, теория игр и прогнозирование. Научные результаты, модели и гипотезы отмечаются отдельно."},
    "culture": {"title": "Культурно-исторический слой", "description": "История идей, религиозная философия, традиции, космизм и представления о бессмертии. Исторические факты отделяются от интерпретаций и легенд."},
    "security": {"title": "Кибербезопасность", "description": "Уязвимости, защита сайтов, API, Docker, n8n, сетей и AI-агентов. Поиск и сбор материалов SecurityLab.ru."},
}
SCIENCE_STREAMS = {
    "science-ai": {"title": "AI и технологии", "description": "Исследования AI, машинного обучения и инженерии. Анонсы требуют проверки первоисточника."},
    "science-neuro": {"title": "Медицина и нейронауки", "description": "Медицинские исследования, нейронауки и общественное здоровье. Новости отделяются от клинических рекомендаций."},
    "science-longevity": {"title": "Долголетие", "description": "Старение, geroscience и продление здоровой жизни. Результаты на людях, животных и клетках рассматриваются раздельно."},
}
ALL_STREAMS = {**STREAMS, **SCIENCE_STREAMS}
FEEDS = {name: f"https://www.securitylab.ru/_Services/Export/RSS/{name}/" for name in ("news", "vulnerabilities", "analytics", "software")}
# SecurityLab still advertises the specialized feed, but it returns HTTP 404.
# The documented main RSS is a fallback, not a claim of identical coverage.
FEED_FALLBACKS = {"vulnerabilities": "https://www.securitylab.ru/_Services/Export/RSS/"}
logger = logging.getLogger(__name__)


def normalize_url(value):
    parts = urlsplit(value.strip())
    if parts.scheme not in ("https", "http") or not parts.hostname or parts.username or parts.password:
        raise ValueError("Нужна ссылка http/https без учётных данных.")
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not k.lower().startswith("utm_") and k.lower() not in ("fbclid", "gclid")]
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path or "/", urlencode(sorted(query)), ""))


def save_material(stream, title, source_url, body="", summary="", evidence="Требует проверки", published_date=""):
    if stream not in ALL_STREAMS or not title.strip():
        raise ValueError("Укажите направление и заголовок.")
    url = normalize_url(source_url)
    existing = LifeOSMaterial.query.filter_by(source_url=url).first()
    if existing:
        return existing, False
    item = LifeOSMaterial(stream=stream, title=title.strip()[:500], source_url=url, body=body[:100000], summary=summary[:2000], evidence=evidence[:80], published_date=published_date[:100])
    if len(url) > 1500:
        raise ValueError("Ссылка слишком длинная.")
    db.session.add(item)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        existing = LifeOSMaterial.query.filter_by(source_url=url).first()
        if not existing:
            raise
        return existing, False
    return item, True


def parse_feed(data):
    if len(data) > 4 * 1024 * 1024:
        raise ValueError("RSS превышает лимит размера.")
    root = ET.fromstring(data)
    if root.tag != "rss":
        raise ValueError("Источник не вернул RSS; возможно, доступ ограничен.")
    results = []
    for node in root.findall("./channel/item"):
        title, link = node.findtext("title", ""), node.findtext("link", "")
        if not title or not link:
            continue
        url = normalize_url(link)
        if urlsplit(url).hostname not in ("securitylab.ru", "www.securitylab.ru"):
            continue
        description = unescape(re.sub(r"<[^>]*>", " ", node.findtext("description", "")))
        results.append({"title": title, "source_url": url, "summary": " ".join(description.split())[:2000], "published_date": node.findtext("pubDate", "")})
    return results


def _read_securitylab_feed(url):
    with requests.get(url, timeout=(5, 15), stream=True) as response:
        response.raise_for_status()
        parts = urlsplit(response.url)
        if parts.scheme != "https" or parts.netloc not in ("securitylab.ru", "www.securitylab.ru"):
            raise ValueError("SecurityLab RSS redirected outside official source")
        data = bytearray()
        for chunk in response.iter_content(65536):
            data.extend(chunk)
            if len(data) > 4 * 1024 * 1024:
                raise ValueError("RSS превышает лимит размера.")
    return parse_feed(bytes(data))


def _fetch_securitylab_feed(url):
    for attempt in range(3):
        try:
            return _read_securitylab_feed(url)
        except (requests.Timeout, requests.ConnectionError):
            if attempt == 2:
                raise
        except requests.HTTPError as exc:
            if exc.response is None or exc.response.status_code not in (500, 502, 503, 504) or attempt == 2:
                raise
        time.sleep(0.5 * (attempt + 1))


def _feed_error(exc):
    response = getattr(exc, "response", None)
    if isinstance(exc, requests.HTTPError) and response is not None:
        return f"HTTP {response.status_code}"
    return type(exc).__name__


def collect_securitylab(*, warnings=None):
    created = 0
    errors = []
    for name, url in FEEDS.items():
        try:
            try:
                rows = _fetch_securitylab_feed(url)
            except requests.HTTPError as exc:
                response = exc.response
                if name not in FEED_FALLBACKS or response is None or response.status_code not in (404, 410):
                    raise
                rows = _fetch_securitylab_feed(FEED_FALLBACKS[name])
                warning = (f"{name}: {_feed_error(exc)}; collected official main RSS instead; "
                           "specialized vulnerability-feed coverage is unavailable")
                logger.warning("%s", warning)
                if warnings is not None:
                    warnings.append(warning)
            for fields in rows:
                _, added = save_material("security", **fields)
                created += added
        except (requests.RequestException, ET.ParseError, ValueError) as exc:
            errors.append(f"{name}: {_feed_error(exc)}")
    return created, errors
