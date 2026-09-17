"""Сборка ответа: единый индекс портала → опциональная модель → эскалация."""

from __future__ import annotations

from typing import Any

from assistant.knowledge import load_knowledge
from assistant.llm import generate_answer
from assistant.retrieve import is_relevant, retrieve

ESCALATE_TEXT = (
    "В материалах сайта этого нет — выдумывать не буду. "
    "Оставьте заявку через форму контактов — разберём задачу лично."
)
MAX_MESSAGE_LEN = 400
MAX_RESULTS = 4


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

    matches = retrieve(text, load_knowledge(), top_k=6)
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

    source = "faq" if best_item.get("kind") == "faq" else "portal"
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
