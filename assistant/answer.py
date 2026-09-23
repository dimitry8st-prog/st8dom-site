"""Сборка ответа: единый индекс портала → опциональная модель → эскалация."""

from __future__ import annotations

from typing import Any

from assistant.knowledge import load_knowledge
from assistant.intents import route_intent
from assistant.llm import generate_answer
from assistant.retrieve import is_relevant, normalize, retrieve, tokenize

ESCALATE_TEXT = (
    "В материалах сайта этого нет — выдумывать не буду. "
    "Оставьте заявку через форму контактов — разберём задачу лично."
)
MAX_MESSAGE_LEN = 400
MAX_RESULTS = 4
LIBRARY_GENERIC_TOKENS = {
    "библиотек",
    "брошюр",
    "методичк",
    "методик",
    "материал",
    "список",
    "весь",
}


def _library_topical_tokens(text: str) -> set[str]:
    """Оставляет тему запроса, убирая все словоформы типа материала."""
    return {
        token
        for token in tokenize(text)
        if token not in LIBRARY_GENERIC_TOKENS
        and not token.startswith(("методич", "методик", "брошюр", "библиотек"))
    }


def normalize_message(raw: str | None) -> str:
    return (raw or "").strip()


def _results(matches: list[tuple[dict[str, Any], float]]) -> list[dict[str, str]]:
    results = []
    seen_urls = set()
    for item, _score in matches:
        url = item.get("url")
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        results.append(
            {
                "title": item.get("title") or item["question"],
                "url": url,
                "kind": item.get("kind_label") or "Материал",
            }
        )
        if len(results) >= MAX_RESULTS:
            break
    return results


def _context_chunk(item: dict[str, Any]) -> str:
    content = (item.get("content") or item["answer"]).strip()
    return (
        f"Название: {item.get('title') or item['question']}\n"
        f"Тип: {item.get('kind_label') or 'Ответ'}\n"
        f"Адрес: {item.get('url') or 'нет'}\n"
        f"Содержание: {content[:2400]}"
    )


def _library_kind(text: str) -> str | None:
    query = normalize(text)
    if "брошюр" in query:
        return "brochure"
    if "методич" in query or "методик" in query:
        return "guide"
    if "библиотек" in query:
        return "all"
    return None


def _is_library_item(item: dict[str, Any], requested_kind: str) -> bool:
    if item.get("kind") != "library":
        return False
    library_kind = normalize(item.get("library_kind", ""))
    if requested_kind == "brochure":
        return library_kind == "брошюра"
    if requested_kind == "guide":
        return library_kind.startswith("методич") or library_kind == "методика"
    return True


def _library_listing(
    text: str,
    knowledge: tuple[dict[str, Any], ...],
) -> dict[str, Any] | None:
    """Даёт точный список вместо генерации, когда пользователь спрашивает виды материалов."""
    requested_kind = _library_kind(text)
    if not requested_kind:
        return None

    topical_tokens = _library_topical_tokens(text)
    if topical_tokens:
        return None

    items = [item for item in knowledge if _is_library_item(item, requested_kind)]
    if not items:
        return None

    if requested_kind == "brochure":
        label = "брошюры"
    elif requested_kind == "guide":
        label = "методических материалов"
    else:
        label = "материалов"

    titles = [item["title"] for item in items[:MAX_RESULTS]]
    remainder = len(items) - len(titles)
    tail = f" и ещё {remainder}" if remainder else ""
    answer = f"В библиотеке ДИС есть {len(items)} {label}: {', '.join(titles)}{tail}."
    matches = [(item, 1.0) for item in items]
    results = _results(matches)
    if len(items) > MAX_RESULTS:
        results = [
            {
                "title": "Все методички и брошюры",
                "url": "/library/",
                "kind": "Библиотека",
            },
            *_results(matches[: MAX_RESULTS - 1]),
        ]
    return {
        "answer": answer,
        "escalated": False,
        "source": "library",
        "results": results,
    }


def answer_question(question: str, app_config: dict | None = None) -> dict[str, Any]:
    text = normalize_message(question)
    if not text:
        return {
            "answer": "Напишите, что найти: статью, рубрику, проект, кейс, услугу или контакт.",
            "escalated": False,
            "source": "empty",
            "results": [],
        }
    if len(text) > MAX_MESSAGE_LEN:
        return {
            "answer": "Сообщение слишком длинное. Сожмите вопрос или сразу оставьте заявку.",
            "escalated": True,
            "source": "limit",
            "results": [],
        }

    knowledge = load_knowledge()
    intent_response = route_intent(text, knowledge)
    if intent_response:
        return intent_response

    library_listing = _library_listing(text, knowledge)
    if library_listing:
        return library_listing

    requested_library_kind = _library_kind(text)
    search_space = knowledge
    if requested_library_kind:
        search_space = tuple(
            item for item in knowledge if _is_library_item(item, requested_library_kind)
        )

    matches = retrieve(text, search_space, top_k=6)
    if requested_library_kind and matches:
        topical_tokens = _library_topical_tokens(text)
        if topical_tokens:
            best_library_score = matches[0][1]
            matches = [
                match
                for match in matches
                if match[1] >= max(0.5, best_library_score - 0.2)
            ]
    best_item, best_score = (matches[0] if matches else (None, 0.0))
    if not best_item or not is_relevant(best_score):
        return {
            "answer": ESCALATE_TEXT,
            "escalated": True,
            "source": "escalate",
            "results": [],
        }

    results = _results(matches)
    chunks = [_context_chunk(item) for item, _score in matches]
    config = app_config or {}
    generated = generate_answer(text, chunks, config)
    if generated:
        return {
            "answer": generated,
            "escalated": False,
            "source": "llm",
            "results": results,
        }

    if best_item.get("kind") == "faq":
        source = "faq"
    elif best_item.get("kind") == "library":
        source = "library"
    else:
        source = "portal"
    if source == "faq":
        answer = best_item["answer"]
    else:
        title = best_item.get("title") or best_item["question"]
        answer = f"Нашёл: «{title}». {best_item['answer']}"
    return {
        "answer": answer,
        "escalated": False,
        "source": source,
        "results": results,
    }
