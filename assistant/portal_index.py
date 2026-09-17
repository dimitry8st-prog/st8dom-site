"""Единый поисковый индекс опубликованного содержимого портала."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from cases import get_all_cases
from editorial import published_articles
from portal_content import PROJECTS, SECTIONS


KIND_LABELS = {
    "article": "Материал",
    "case": "Кейс",
    "project": "Проект",
    "direction": "Раздел",
    "topic": "Тема",
    "rubric": "Рубрика",
    "page": "Страница",
}


def _document(
    item_id: str,
    title: str,
    answer: str,
    url: str,
    kind: str,
    *,
    aliases: list[str] | None = None,
    content: str = "",
) -> dict[str, Any]:
    return {
        "id": item_id,
        "question": title,
        "title": title,
        "answer": answer,
        "aliases": aliases or [],
        "search_text": content,
        "content": content or answer,
        "url": url,
        "kind": kind,
        "kind_label": KIND_LABELS[kind],
    }


def _static_pages() -> list[dict[str, Any]]:
    return [
        _document(
            "page-home",
            "Главная страница портала ДИС",
            "Портал о медицине, AI, долголетии, Life-OS и проектах Дмитрия Степанова.",
            "/",
            "page",
            aliases=["главная", "портал дис", "st8dom"],
        ),
        _document(
            "page-author",
            "Об авторе — Дмитрий Степанов",
            "Информация об авторе портала, медицинском опыте, образовании и направлениях разработки.",
            "/#about",
            "page",
            aliases=["автор", "дмитрий степанов", "степанов дмитрий", "обо мне"],
        ),
        _document(
            "page-materials",
            "Все материалы",
            "Опубликованные статьи, обзоры, рекомендации и разборы портала.",
            "/materials/",
            "page",
            aliases=["статьи", "публикации", "обзоры", "материалы"],
        ),
        _document(
            "page-projects",
            "Все проекты",
            "Витрина разработанных AI-систем, ассистентов и автоматизаций.",
            "/projects/",
            "page",
            aliases=["портфолио", "репозитории", "проекты"],
        ),
        _document(
            "page-cases",
            "Подробные кейсы",
            "Разборы задач, архитектуры, результатов, проверок и ограничений проектов.",
            "/cases/",
            "page",
            aliases=["кейсы", "примеры работ"],
        ),
        _document(
            "page-contact",
            "Контакты и заявка",
            "Форма связи с Дмитрием Степановым для обсуждения задачи или проекта.",
            "/contact/",
            "page",
            aliases=["контакты", "связаться", "написать", "заявка", "обратная связь"],
        ),
        _document(
            "page-telegram",
            "Telegram-бот готовится",
            "Новый Telegram-бот портала находится в разработке.",
            "/telegram/",
            "page",
            aliases=["telegram", "телеграм", "бот"],
        ),
    ]


def _direction_documents() -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    for section_slug, section in SECTIONS.items():
        section_url = f"/directions/{section_slug}/"
        documents.append(
            _document(
                f"direction-{section_slug}",
                section["title"],
                section["summary"],
                section_url,
                "direction",
                aliases=[section["eyebrow"]],
                content=" ".join([section["description"], *section.get("principles", [])]),
            )
        )
        for topic in section["topics"]:
            topic_url = f"/directions/{section_slug}/{topic['slug']}/"
            rubric_names = [name for _slug, name in topic["rubrics"]]
            documents.append(
                _document(
                    f"topic-{section_slug}-{topic['slug']}",
                    topic["title"],
                    topic["description"],
                    topic_url,
                    "topic",
                    aliases=rubric_names,
                    content=f"{section['title']} {' '.join(rubric_names)}",
                )
            )
            for rubric_slug, rubric_name in topic["rubrics"]:
                full_slug = f"{topic['slug']}-{rubric_slug}"
                query = urlencode({"section": section_slug, "rubric": full_slug})
                documents.append(
                    _document(
                        f"rubric-{section_slug}-{full_slug}",
                        rubric_name,
                        f"Рубрика раздела «{topic['title']}». {topic['description']}",
                        f"/materials/?{query}",
                        "rubric",
                        aliases=[section["title"], topic["title"]],
                    )
                )
    return documents


def _case_and_project_documents() -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    case_slugs = set()
    for case in get_all_cases():
        case_slugs.add(case["slug"])
        searchable_parts = [
            case.get("problem"),
            case.get("solution"),
            case.get("architecture"),
            case.get("now_works"),
            case.get("verification"),
            case.get("limitations"),
            case.get("status"),
            " ".join(case.get("filters", [])),
            " ".join(case.get("tech", [])),
        ]
        documents.append(
            _document(
                f"case-{case['slug']}",
                case["title"],
                case["card_summary"],
                f"/cases/{case['slug']}/",
                "case",
                aliases=[case.get("short_title", ""), case.get("type", "")],
                content=" ".join(str(part) for part in searchable_parts if part),
            )
        )

    for project in PROJECTS:
        if project.get("case_slug") in case_slugs:
            continue
        repo = project.get("repo") or ""
        documents.append(
            _document(
                f"project-{repo or project['name']}",
                project["name"],
                project["summary"],
                "/projects/",
                "project",
                aliases=[repo, *project.get("areas", [])],
            )
        )
    return documents


def _published_article_documents() -> list[dict[str, Any]]:
    """Читает живые публикации только внутри Flask application context."""
    try:
        articles = published_articles().all()
    except RuntimeError:
        return []

    documents = []
    for article in articles:
        tag_names = [tag.name for tag in article.tags]
        source_titles = [source.title for source in article.sources]
        rubric_name = article.rubric.name if article.rubric else ""
        documents.append(
            _document(
                f"article-{article.id}",
                article.title,
                article.summary,
                f"/materials/{article.slug}/",
                "article",
                aliases=[rubric_name, *tag_names],
                content=" ".join([article.body, *source_titles]),
            )
        )
    return documents


def load_portal_documents() -> tuple[dict[str, Any], ...]:
    """Собирает статическую навигацию и актуальные публикации одним списком."""
    documents = [
        *_static_pages(),
        *_direction_documents(),
        *_case_and_project_documents(),
        *_published_article_documents(),
    ]
    return tuple(documents)
