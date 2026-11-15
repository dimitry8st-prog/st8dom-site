"""Обновляет GitHub-реестр и Obsidian-заметки из официального API Минздрава."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from clinical_guidelines import (
    GUIDELINE_SPECIALTIES,
    OFFICIAL_SOURCES,
    _minzdrav_payload,
    classify_guideline_specialties,
    fetch_aao_hnsf_guidelines,
    fetch_minzdrav_page,
    is_neurology_or_neurosurgery,
)

REGISTRY_PATH = ROOT / "data" / "clinical_guidelines.json"
VAULT_DIR = ROOT / "obsidian-vault" / "Клинические рекомендации" / "Входящие"


def _yaml_string(value) -> str:
    return json.dumps(str(value or ""), ensure_ascii=False)


def _safe_filename(source_key: str, external_id: str) -> str:
    stem = re.sub(r"[^0-9A-Za-zА-Яа-я_-]+", "-", f"{source_key}-{external_id}")
    return f"{stem.strip('-')[:140]}.md"


def render_obsidian_note(item: dict) -> str:
    """Создаёт детерминированную заметку без медицинской интерпретации AI."""
    fields = {
        "type": "clinical-guideline",
        "review_status": "needs-human-review",
        "source_key": item["source_key"],
        "external_id": item["external_id"],
        "title": item["title"],
        "organization": item.get("organization"),
        "version": item.get("version"),
        "published_on": item.get("published_on"),
        "codes": item.get("codes"),
        "specialties": item.get("specialties"),
        "specialty_tags": ",".join(item.get("specialty_tags") or []),
        "official_url": item["url"],
        "source_status": item.get("status", "active"),
    }
    frontmatter = "\n".join(f"{key}: {_yaml_string(value)}" for key, value in fields.items())
    specialty_tags = item.get("specialty_tags") or []
    profile_tags = ", ".join(
        GUIDELINE_SPECIALTIES[slug].casefold()
        for slug in specialty_tags
        if slug in GUIDELINE_SPECIALTIES
    )
    return (
        f"---\n{frontmatter}\n"
        f"tags: [клинические-рекомендации, {profile_tags or 'другой-профиль'}, на-проверку]\n"
        "---\n\n"
        f"# {item['title']}\n\n"
        "## Официальная карточка\n\n"
        f"- Источник: [{OFFICIAL_SOURCES[item['source_key']]['name']}]({item['url']})\n"
        f"- Организация: {item.get('organization') or 'не указана'}\n"
        f"- Версия: {item.get('version') or 'не указана'}\n"
        f"- Коды МКБ: {item.get('codes') or 'не указаны'}\n\n"
        "## Рабочие заметки\n\n"
        "> Заполняются после изучения оригинала. AI не формирует медицинские выводы автоматически.\n\n"
        "## Проверка Степановым Д.А.\n\n"
        "- [ ] Открыт официальный документ\n"
        "- [ ] Проверены актуальность и версия\n"
        "- [ ] Подготовлены практические выводы с точными ссылками\n"
        "- [ ] Материал допущен в RAG\n"
    )


def load_registry() -> dict[tuple[str, str], dict]:
    if not REGISTRY_PATH.exists():
        return {}
    payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    return {
        (item["source_key"], item["external_id"]): item
        for item in payload.get("items", [])
    }


def write_registry_and_notes(registry: dict[tuple[str, str], dict]) -> int:
    """Нормализует профили и сохраняет текущий реестр без сетевых запросов."""
    for item in registry.values():
        item["specialty_tags"] = list(classify_guideline_specialties(item))
    items = sorted(
        registry.values(), key=lambda row: (row["source_key"], row["title"].casefold())
    )
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_PATH.write_text(
        json.dumps({"schema_version": 1, "items": items}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    for item in items:
        note = VAULT_DIR / _safe_filename(item["source_key"], item["external_id"])
        note.write_text(render_obsidian_note(item), encoding="utf-8")
    return len(items)


def _source_error(exc: Exception) -> str:
    """В отчёт попадает причина, но не тело ответа или данные окружения."""
    response = getattr(exc, "response", None)
    if isinstance(exc, requests.HTTPError) and response is not None:
        return f"HTTP {response.status_code}"
    return type(exc).__name__


def sync(pages: int, full: bool = False, registry_only: bool = False) -> dict:
    registry = load_registry()
    if registry_only:
        return {
            "ok": True,
            "scanned": 0,
            "matched": 0,
            "international": 0,
            "stored": write_registry_and_notes(registry),
            "sources": {},
            "errors": [],
        }
    scanned = matched = 0
    sources, errors = {}, []
    # Изменения источника сливаются только после успешного прохода всех его
    # запрошенных страниц. Другой источник проверяется даже при первом сбое.
    russian = {}
    try:
        current_page = 1
        while True:
            source_data = fetch_minzdrav_page(current_page=current_page, page_size=50)
            rows = source_data["Data"]
            scanned += len(rows)
            for source_item in rows:
                if not source_item.get("NPC_approved") or not is_neurology_or_neurosurgery(source_item):
                    continue
                item = _minzdrav_payload(source_item)
                russian[(item["source_key"], item["external_id"])] = item
                matched += 1
            total = int(source_data["TotalRecords"])
            if not rows or scanned >= total or (not full and current_page >= pages):
                break
            current_page += 1
            if current_page > 40:
                raise RuntimeError("Остановлено после 40 страниц: проверьте API Минздрава.")
        registry.update(russian)
        sources["minzdrav"] = {"ok": True, "scanned": scanned, "matched": matched}
    except (requests.RequestException, ValueError, RuntimeError) as exc:
        error = _source_error(exc)
        sources["minzdrav"] = {"ok": False, "scanned": scanned, "matched": matched, "error": error}
        errors.append(f"minzdrav: {error}")

    international = []
    try:
        international = fetch_aao_hnsf_guidelines()
        additions = {
            (item["source_key"], item["external_id"]): item for item in international
        }
        registry.update(additions)
        sources["aao_hnsf"] = {"ok": True, "matched": len(international)}
    except (requests.RequestException, ValueError, RuntimeError) as exc:
        error = _source_error(exc)
        sources["aao_hnsf"] = {"ok": False, "error": error}
        errors.append(f"aao_hnsf: {error}")

    return {
        "ok": not errors,
        "scanned": scanned,
        "matched": matched,
        "international": len(international),
        "stored": write_registry_and_notes(registry),
        "sources": sources,
        "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pages", type=int, default=5)
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--report-file", type=Path, help="JSON-отчёт о результате каждого источника.")
    parser.add_argument(
        "--registry-only",
        action="store_true",
        help="Обновить профили и Obsidian-заметки из локального JSON без сети.",
    )
    args = parser.parse_args()
    result = sync(max(1, args.pages), args.full, args.registry_only)
    result["checked_at"] = datetime.now(timezone.utc).isoformat()
    report = json.dumps(result, ensure_ascii=False)
    print(report)
    if args.report_file:
        args.report_file.write_text(report + "\n", encoding="utf-8")
    if not result["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
