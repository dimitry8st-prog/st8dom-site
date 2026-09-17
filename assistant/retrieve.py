"""Поиск по FAQ без FAISS и sentence-transformers — база на десятки карточек."""

from __future__ import annotations

import re
from typing import Any

WORD_RE = re.compile(r"[а-яa-z0-9]{2,}", re.IGNORECASE)
STOPWORDS = {
    "как",
    "что",
    "это",
    "для",
    "или",
    "при",
    "по",
    "на",
    "без",
    "есть",
    "ваш",
    "вас",
    "мне",
    "нас",
    "про",
    "том",
    "этой",
    "этот",
    "эта",
    "ли",
    "же",
    "бы",
    "вы",
    "ты",
    "мы",
    "он",
    "она",
    "где",
    "найти",
    "найди",
    "покажи",
    "расскажи",
    "какой",
    "какая",
    "какие",
    "каких",
    "сколько",
    "перечисли",
    "все",
    "имеются",
    "доступны",
    "доступно",
    "доступных",
}
ENDINGS = (
    "иями",
    "ями",
    "ами",
    "ого",
    "ему",
    "ыми",
    "ими",
    "иях",
    "ией",
    "ах",
    "ях",
    "ия",
    "ию",
    "ии",
    "ов",
    "ев",
    "ой",
    "ей",
    "ом",
    "ем",
    "ий",
    "ый",
    "ая",
    "ое",
    "ые",
    "ие",
    "ть",
    "а",
    "я",
    "ы",
    "и",
    "у",
    "ю",
    "е",
)


def normalize(text: str) -> str:
    return text.lower().replace("ё", "е")


def contains_phrase(text: str, phrase: str) -> bool:
    """Ищет слово или фразу целиком, не совпадая с частью другого слова."""
    if not phrase:
        return False
    pattern = rf"(?<![а-яa-z0-9]){re.escape(phrase)}(?![а-яa-z0-9])"
    return re.search(pattern, text, re.IGNORECASE) is not None


def stem(word: str) -> str:
    token = normalize(word)
    for ending in ENDINGS:
        if token.endswith(ending) and len(token) - len(ending) >= 4:
            return token[: -len(ending)]
    return token


def tokenize(text: str) -> set[str]:
    words = WORD_RE.findall(normalize(text))
    tokens = {stem(word) for word in words if word not in STOPWORDS}
    return {token for token in tokens if len(token) >= 2}


def _score_item(query: str, query_tokens: set[str], item: dict[str, Any]) -> float:
    title_text = " ".join([item["question"], *item.get("aliases", [])])
    title_tokens = tokenize(title_text)
    body_tokens = tokenize(" ".join([item["answer"], item.get("search_text", "")]))
    if not query_tokens:
        return 0.0

    title_hits = len(query_tokens & title_tokens)
    body_hits = len(query_tokens & body_tokens)
    coverage = title_hits / len(query_tokens)
    # Одно точное редкое слово из текста статьи (например, название препарата)
    # должно находить материал, даже если его нет в заголовке.
    score = coverage + (body_hits / len(query_tokens)) * 0.45

    query_norm = normalize(query)
    if normalize(item["question"]) in query_norm or query_norm in normalize(item["question"]):
        score += 0.35
    for alias in item.get("aliases", []):
        alias_norm = normalize(alias)
        if alias_norm and (
            contains_phrase(query_norm, alias_norm)
            or contains_phrase(alias_norm, query_norm)
        ):
            score += 0.4
            break
    return score


def retrieve(
    question: str,
    faqs: tuple[dict[str, Any], ...] | list[dict[str, Any]],
    top_k: int = 3,
) -> list[tuple[dict[str, Any], float]]:
    query_tokens = tokenize(question)
    ranked: list[tuple[dict[str, Any], float]] = []
    for item in faqs:
        ranked.append((item, _score_item(question, query_tokens, item)))
    ranked.sort(key=lambda pair: pair[1], reverse=True)
    return [pair for pair in ranked[:top_k] if pair[1] > 0]


def is_relevant(score: float, threshold: float = 0.38) -> bool:
    return score >= threshold
