"""Кураторский каталог промптов из редакционных JSON-файлов."""

import json
from pathlib import Path


PROMPT_DIR = Path(__file__).resolve().parent / "data" / "prompts"
CATEGORIES = (
    ("work", "Для работы"),
    ("analysis", "Для анализа"),
    ("content", "Для контента"),
    ("verification", "Проверка результата"),
)
CATEGORY_NAMES = dict(CATEGORIES)


def all_prompts():
    """Читает только файлы, включённые в репозиторий, в стабильном порядке."""
    result = []
    for category, _ in CATEGORIES:
        for path in sorted((PROMPT_DIR / category).glob("*.json")):
            item = json.loads(path.read_text(encoding="utf-8"))
            result.append({**item, "slug": path.stem, "category": category})
    return result


def find_prompt(category, slug):
    if category not in CATEGORY_NAMES or not slug or "/" in slug or "\\" in slug:
        return None
    return next(
        (item for item in all_prompts() if item["category"] == category and item["slug"] == slug),
        None,
    )
