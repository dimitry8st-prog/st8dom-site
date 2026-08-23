"""Загрузка FAQ сайта. Без векторной БД: база небольшая и правится в git."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from config import BASE_DIR

FAQ_PATH = BASE_DIR / "data" / "faqs.json"


@lru_cache(maxsize=1)
def _load_faqs_cached(mtime: float) -> tuple[dict[str, Any], ...]:
    path = Path(FAQ_PATH)
    raw = json.loads(path.read_text(encoding="utf-8"))
    items = []
    for row in raw:
        question = str(row.get("question", "")).strip()
        answer = str(row.get("answer", "")).strip()
        if not question or not answer:
            continue
        aliases = [str(alias).strip() for alias in row.get("aliases", []) if str(alias).strip()]
        items.append(
            {
                "id": str(row.get("id") or question),
                "question": question,
                "answer": answer,
                "aliases": aliases,
            }
        )
    return tuple(items)


def load_faqs() -> tuple[dict[str, Any], ...]:
    mtime = Path(FAQ_PATH).stat().st_mtime
    return _load_faqs_cached(mtime)


def reload_faqs() -> tuple[dict[str, Any], ...]:
    _load_faqs_cached.cache_clear()
    return load_faqs()
