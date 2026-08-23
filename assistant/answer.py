"""Сборка ответа: релевантная FAQ → опциональная модель → иначе эскалация."""

from __future__ import annotations

from typing import Any

from assistant.knowledge import load_faqs
from assistant.llm import generate_answer
from assistant.retrieve import is_relevant, retrieve

ESCALATE_TEXT = (
    "В материалах сайта этого нет — выдумывать не буду. "
    "Оставьте заявку или напишите в Telegram, разберём задачу лично."
)
MAX_MESSAGE_LEN = 400


def normalize_message(raw: str | None) -> str:
    return (raw or "").strip()


def answer_question(question: str, app_config: dict | None = None) -> dict[str, Any]:
    text = normalize_message(question)
    if not text:
        return {
            "answer": "Напишите вопрос текстом — отвечу по услугам, кейсам и тому, как начать.",
            "escalated": False,
            "source": "empty",
        }
    if len(text) > MAX_MESSAGE_LEN:
        return {
            "answer": "Сообщение слишком длинное. Сожмите вопрос или сразу оставьте заявку.",
            "escalated": True,
            "source": "limit",
        }

    matches = retrieve(text, load_faqs())
    best_item, best_score = (matches[0] if matches else (None, 0.0))
    if not best_item or not is_relevant(best_score):
        return {"answer": ESCALATE_TEXT, "escalated": True, "source": "escalate"}

    chunks = [f"Вопрос: {item['question']}\nОтвет: {item['answer']}" for item, _score in matches]
    config = app_config or {}
    generated = generate_answer(text, chunks, config)
    if generated:
        return {"answer": generated, "escalated": False, "source": "llm"}
    return {"answer": best_item["answer"], "escalated": False, "source": "faq"}
