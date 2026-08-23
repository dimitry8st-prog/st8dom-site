"""Опциональная формулировка ответа. Без ключа модуль ничего не вызывает."""

from __future__ import annotations

import logging

import requests

logger = logging.getLogger("st8dom")

SYSTEM_PROMPT = (
    "Ты — ассистент сайта st8dom.ru Дмитрия Степанова. "
    "Отвечай только на основе контекста FAQ. "
    "Не выдумывай цены, клиентов и сроки, которых нет в контексте. "
    "Если ответа нет в контексте, напиши ровно: OUT_OF_SCOPE. "
    "Отвечай кратко, по делу, на русском."
)


def _user_prompt(question: str, context_chunks: list[str]) -> str:
    context = "\n\n---\n\n".join(context_chunks) if context_chunks else "Контекст отсутствует."
    return (
        f"Контекст из базы сайта:\n{context}\n\n"
        f"Вопрос посетителя:\n{question}\n\n"
        "Ответь, используя только контекст выше."
    )


def _ask_openai(question: str, context_chunks: list[str], app_config: dict) -> str:
    key = app_config.get("OPENAI_API_KEY") or ""
    model = app_config.get("OPENAI_MODEL") or "gpt-4o-mini"
    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "temperature": 0.2,
            "max_tokens": 280,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _user_prompt(question, context_chunks)},
            ],
        },
        timeout=10,
    )
    response.raise_for_status()
    data = response.json()
    return ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""


def _ask_claude(question: str, context_chunks: list[str], app_config: dict) -> str:
    key = app_config.get("CLAUDE_API_KEY") or ""
    model = app_config.get("CLAUDE_MODEL") or "claude-haiku-4-5-20251001"
    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "max_tokens": 280,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": _user_prompt(question, context_chunks)}],
        },
        timeout=10,
    )
    response.raise_for_status()
    data = response.json()
    parts = [block.get("text", "") for block in data.get("content", []) if block.get("type") == "text"]
    return "\n".join(parts)


def generate_answer(question: str, context_chunks: list[str], app_config: dict) -> str | None:
    """Вернёт текст модели или None, если ключа нет / запрос не удался / вне базы."""
    provider = (app_config.get("LLM_PROVIDER") or "openai").lower()
    try:
        if provider == "claude":
            if not app_config.get("CLAUDE_API_KEY"):
                return None
            text = _ask_claude(question, context_chunks, app_config)
        else:
            if not app_config.get("OPENAI_API_KEY"):
                return None
            text = _ask_openai(question, context_chunks, app_config)
    except requests.RequestException:
        logger.warning("LLM недоступна, оставляю ответ из FAQ", exc_info=True)
        return None

    cleaned = (text or "").strip()
    if not cleaned or cleaned == "OUT_OF_SCOPE":
        return None
    return cleaned
