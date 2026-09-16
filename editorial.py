"""Редакционная логика портала: безопасные публикации и связи материалов."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import urlparse

from extensions import db
from models import Article, ArticleSource, Rubric, Tag


STATUS_LABELS = {
    "draft": "Черновик",
    "review": "На проверке",
    "ready": "Готово",
    "published": "Опубликовано",
    "archive": "Архив",
}

CONTENT_TYPE_LABELS = {
    "article": "Статья",
    "review": "Обзор",
    "recommendation": "Рекомендация",
    "analysis": "Разбор",
    "patient": "Материал пациенту",
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def tag_slug(value: str) -> str:
    """Стабильный URL-совместимый идентификатор для русских и латинских тегов."""
    return re.sub(r"[^\w]+", "-", value.casefold(), flags=re.UNICODE).strip("-")


def parse_tags(raw: str) -> list[str]:
    result = []
    seen = set()
    for part in raw.split(","):
        name = part.strip()
        key = name.casefold()
        if name and key not in seen:
            seen.add(key)
            result.append(name)
    return result


def parse_sources(raw: str) -> tuple[list[tuple[str, str]], list[str]]:
    """Читает строки `Название | URL` и отклоняет небезопасные адреса."""
    sources = []
    errors = []
    seen_urls = set()
    for number, line in enumerate(raw.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        if "|" not in line:
            errors.append(f"Источник {number}: добавьте разделитель | между названием и URL.")
            continue
        title, url = (part.strip() for part in line.split("|", 1))
        parsed = urlparse(url)
        if not title:
            errors.append(f"Источник {number}: отсутствует название.")
        elif parsed.scheme not in {"http", "https"} or not parsed.netloc:
            errors.append(f"Источник {number}: нужен полный адрес http(s).")
        elif url not in seen_urls:
            seen_urls.add(url)
            sources.append((title, url))
    return sources, errors


def sources_as_text(article: Article) -> str:
    return "\n".join(f"{source.title} | {source.url}" for source in article.sources)


def apply_article_form(article: Article, form) -> list[str]:
    """Применяет проверенную форму, не разрешая обойти кнопку публикации."""
    sources, source_errors = parse_sources(form.sources.data or "")
    if source_errors:
        return source_errors
    rubric = db.session.get(Rubric, form.rubric_id.data)
    if rubric is None or rubric.section != form.section.data:
        return ["Выбранная рубрика не относится к указанному разделу."]

    article.title = form.title.data.strip()
    article.slug = form.slug.data.strip().lower()
    article.summary = form.summary.data.strip()
    article.body = form.body.data.strip()
    article.section = form.section.data
    article.rubric_id = form.rubric_id.data
    article.content_type = form.content_type.data
    article.status = form.status.data
    article.author = form.author.data.strip()
    article.medical_reviewer = (form.medical_reviewer.data or "").strip() or None
    article.disclaimer = (form.disclaimer.data or "").strip() or None
    article.revision_note = (form.revision_note.data or "").strip() or None
    article.is_featured = bool(form.is_featured.data)
    article.reviewed_at = utcnow() if form.reviewed_confirmed.data else None

    tags = []
    for name in parse_tags(form.tags.data or ""):
        slug = tag_slug(name)
        tag = Tag.query.filter_by(slug=slug).first()
        if tag is None:
            tag = Tag(name=name, slug=slug)
        tags.append(tag)
    article.tags = tags

    article.sources.clear()
    article.sources.extend(
        ArticleSource(title=title, url=url) for title, url in sources
    )
    return []


def ensure_editorial_seed() -> None:
    """Создаёт один проверенный стартовый материал для первого вертикального среза."""
    rubric = Rubric.query.filter_by(slug="medical-ai").first()
    if rubric is None:
        rubric = Rubric(
            name="Медицинский AI",
            slug="medical-ai",
            section="medicine",
            description="Безопасное применение AI для поиска и разбора медицинских источников.",
        )
        db.session.add(rubric)

    if Article.query.filter_by(slug="kak-vitalis-proveryaet-istochniki").first():
        db.session.commit()
        return

    tags = []
    for name in ["Медицина", "AI", "RAG", "Источники"]:
        slug = tag_slug(name)
        tag = Tag.query.filter_by(slug=slug).first() or Tag(name=name, slug=slug)
        tags.append(tag)

    article = Article(
        title="Как Vitalis проверяет медицинские источники",
        slug="kak-vitalis-proveryaet-istochniki",
        summary=(
            "Коротко о том, как российский и международный контуры Vitalis ищут "
            "материалы, показывают источники и сохраняют решение за врачом."
        ),
        body=(
            "Vitalis разделяет российский и международный поиск. Это помогает не "
            "смешивать документы разных систем здравоохранения и сразу видеть, к "
            "какому контуру относится найденный материал.\n\n"
            "Сначала система проверяет локальную базу знаний, затем дополняет ответ "
            "веб-поиском. Российская ветка отдаёт приоритет официальным клиническим "
            "рекомендациям, профильным НМИЦ и профессиональным медицинским источникам.\n\n"
            "Найденный материал не попадает в базу знаний автоматически. Он получает "
            "статус кандидата и должен быть проверен человеком. Если веб-поиск "
            "недоступен или подтверждений недостаточно, это ограничение показывается "
            "в ответе.\n\n"
            "Vitalis остаётся справочным инструментом. Окончательная оценка источника, "
            "его применимости и клиническое решение принадлежат специалисту."
        ),
        section="medicine",
        rubric=rubric,
        content_type="analysis",
        status="published",
        author="Степанов Д.А.",
        medical_reviewer="Степанов Д.А.",
        disclaimer=(
            "Материал носит информационный характер, не ставит диагноз и не заменяет "
            "клиническое решение врача."
        ),
        is_featured=True,
        reviewed_at=utcnow(),
        published_at=utcnow(),
        tags=tags,
        sources=[
            ArticleSource(
                title="Vitalis Medical AI — открытый репозиторий проекта",
                url="https://github.com/dimitry8st-prog/Vitalis-Medical-AI",
            )
        ],
    )
    db.session.add(article)
    db.session.commit()


def published_articles():
    return Article.query.filter_by(status="published").filter(
        Article.published_at.is_not(None)
    )


def related_articles(article: Article, limit: int = 3) -> list[Article]:
    own_tags = {tag.slug for tag in article.tags}
    candidates = published_articles().filter(Article.id != article.id).all()
    ranked = sorted(
        candidates,
        key=lambda item: (
            len(own_tags & {tag.slug for tag in item.tags}),
            item.section == article.section,
            item.published_at,
        ),
        reverse=True,
    )
    return ranked[:limit]


def recommended_for_case(case: dict, limit: int = 3) -> list[Article]:
    keywords = {
        str(value).casefold()
        for value in [case.get("slug"), *case.get("filters", []), *case.get("tech", [])]
        if value
    }
    candidates = published_articles().all()

    def score(article: Article):
        article_keys = {tag.name.casefold() for tag in article.tags} | {
            tag.slug.casefold() for tag in article.tags
        }
        return (len(keywords & article_keys), article.is_featured, article.published_at)

    return sorted(candidates, key=score, reverse=True)[:limit]
