"""Безопасный и повторяемый импорт JSON-пакетов Life-OS только в черновики."""

from __future__ import annotations

import hashlib
import json
import re
from urllib.parse import urlparse

from extensions import db
from models import Article, ArticleSource, ImportPackage, Rubric, Tag
from portal_content import SECTIONS
from editorial import CONTENT_TYPE_LABELS, tag_slug

PACKAGE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,119}$")
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class ImportValidationError(ValueError):
    pass


def _text(value, field: str, minimum: int, maximum: int) -> str:
    if not isinstance(value, str):
        raise ImportValidationError(f"{field}: ожидается строка.")
    value = value.strip()
    if not minimum <= len(value) <= maximum:
        raise ImportValidationError(f"{field}: длина должна быть от {minimum} до {maximum} символов.")
    return value


def import_lifeos_package(raw: str):
    if not isinstance(raw, str) or len(raw) > 250_000:
        raise ImportValidationError("Пакет пустой или превышает 250 КБ.")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ImportValidationError(f"Некорректный JSON: строка {exc.lineno}.") from exc
    if not isinstance(payload, dict):
        raise ImportValidationError("Корень пакета должен быть JSON-объектом.")

    package_id = _text(payload.get("package_id"), "package_id", 3, 120)
    if not PACKAGE_ID_RE.fullmatch(package_id):
        raise ImportValidationError("package_id содержит недопустимые символы.")
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    checksum = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    existing = ImportPackage.query.filter_by(package_id=package_id).first()
    if existing:
        if existing.checksum != checksum:
            raise ImportValidationError("package_id уже использован другим содержимым.")
        return existing, False

    version = _text(payload.get("generator_version"), "generator_version", 1, 80)
    article_data = payload.get("article")
    if not isinstance(article_data, dict):
        raise ImportValidationError("article: ожидается объект.")

    title = _text(article_data.get("title"), "article.title", 5, 220)
    slug = _text(article_data.get("slug"), "article.slug", 3, 220).lower()
    if not SLUG_RE.fullmatch(slug):
        raise ImportValidationError("article.slug: нужны латинские буквы, цифры и дефисы.")
    if Article.query.filter_by(slug=slug).first():
        raise ImportValidationError("Материал с таким постоянным адресом уже существует.")
    summary = _text(article_data.get("summary"), "article.summary", 20, 600)
    body = _text(article_data.get("body"), "article.body", 80, 50_000)
    section = _text(article_data.get("section"), "article.section", 2, 40)
    if section not in SECTIONS:
        raise ImportValidationError("article.section: неизвестный раздел.")
    rubric_slug = _text(article_data.get("rubric"), "article.rubric", 3, 120)
    rubric = Rubric.query.filter_by(slug=rubric_slug, section=section).first()
    if rubric is None:
        raise ImportValidationError("article.rubric: рубрика не найдена в указанном разделе.")
    content_type = article_data.get("content_type", "article")
    if content_type not in CONTENT_TYPE_LABELS:
        raise ImportValidationError("article.content_type: неизвестный тип.")

    raw_tags = article_data.get("tags", [])
    if not isinstance(raw_tags, list) or not 1 <= len(raw_tags) <= 20:
        raise ImportValidationError("article.tags: нужен список от 1 до 20 тегов.")
    tags = []
    seen_tags = set()
    for raw_tag in raw_tags:
        name = _text(raw_tag, "article.tags[]", 1, 80)
        key = tag_slug(name)
        if key and key not in seen_tags:
            seen_tags.add(key)
            tags.append(Tag.query.filter_by(slug=key).first() or Tag(name=name, slug=key))

    raw_sources = payload.get("sources", [])
    if not isinstance(raw_sources, list) or len(raw_sources) > 30:
        raise ImportValidationError("sources: ожидается список до 30 источников.")
    sources = []
    seen_urls = set()
    for source in raw_sources:
        if not isinstance(source, dict):
            raise ImportValidationError("sources[]: ожидается объект.")
        source_title = _text(source.get("title"), "sources[].title", 2, 300)
        url = _text(source.get("url"), "sources[].url", 8, 1000)
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ImportValidationError("sources[].url: нужен полный адрес http(s).")
        if url not in seen_urls:
            seen_urls.add(url)
            sources.append(ArticleSource(title=source_title, url=url))

    article = Article(
        title=title,
        slug=slug,
        summary=summary,
        body=body,
        section=section,
        rubric=rubric,
        content_type=content_type,
        status="draft",
        author="Степанов Д.А.",
        tags=tags,
        sources=sources,
    )
    record = ImportPackage(
        package_id=package_id,
        checksum=checksum,
        generator_version=version,
        status="imported",
        article=article,
    )
    db.session.add(record)
    db.session.commit()
    return record, True
