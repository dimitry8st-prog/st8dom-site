from datetime import datetime, timezone
from types import SimpleNamespace

from scripts.export_vitalis_lifeos import build_export


NOW = datetime(2026, 11, 7, tzinfo=timezone.utc)


def article(**overrides):
    values = {
        "section": "medicine",
        "status": "published",
        "published_at": NOW,
        "medical_reviewer": "Степанов Д.А.",
        "reviewed_at": NOW,
        "updated_at": NOW,
        "rubric": SimpleNamespace(slug="neurology-neurosurgery-neurology-treatment"),
        "slug": "migraine-review",
        "title": "Мигрень",
        "summary": "Проверенный обзор",
        "body": "Проверенный клинический текст. " * 10,
        "author": "Степанов Д.А.",
        "tags": [SimpleNamespace(name="Мигрень")],
        "sources": [
            SimpleNamespace(
                title="КР Минздрава",
                url="https://cr.minzdrav.gov.ru/view-cr/295_4",
                accessed_at=NOW,
            )
        ],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_only_published_medically_reviewed_neuro_articles_are_approved():
    draft = article(slug="draft", status="draft")
    unreviewed = article(slug="unreviewed", reviewed_at=None)
    unrelated = article(
        slug="unrelated", rubric=SimpleNamespace(slug="mental-health-depression")
    )
    payload = build_export(
        [article(), draft, unreviewed, unrelated], [], site_url="https://st8dom.ru"
    )
    assert len(payload["approved_records"]) == 1
    record = payload["approved_records"][0]
    assert record["source_id"] == "portal-article-migraine-review"
    assert record["reviewed_by"] == "Степанов Д.А."
    assert record["content_scope"] == "reviewed_excerpt"
    assert record["portal_url"] == "https://st8dom.ru/materials/migraine-review/"


def test_raw_lifeos_neuro_material_is_candidate_not_approved():
    candidate = SimpleNamespace(
        id=42,
        stream="science-neuro",
        title="Новое исследование",
        source_url="https://example.org/study",
        evidence="Подтверждённый научный результат",
        created_at=NOW,
        body="raw material",
    )
    payload = build_export([], [candidate], site_url="https://st8dom.ru")
    assert payload["approved_records"] == []
    assert payload["candidates"][0]["review_status"] == "needs_medical_review"
    assert "body" not in payload["candidates"][0]
