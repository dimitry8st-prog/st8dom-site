"""Безопасная синхронизация клинических рекомендаций."""

import json

from app import app
from clinical_guidelines import (
    GuidelineValidationError,
    sync_guidelines_registry,
    sync_minzdrav,
    upsert_guideline,
)
from extensions import db
from models import ClinicalGuideline


def cleanup(source_key: str, external_id: str) -> None:
    with app.app_context():
        record = ClinicalGuideline.query.filter_by(
            source_key=source_key, external_id=external_id
        ).first()
        if record:
            db.session.delete(record)
            db.session.commit()


def minzdrav_item(code_version="test-neuro-1"):
    return {
        "Id": 90001,
        "Name": "Ишемический инсульт",
        "NPC_approved": True,
        "PublishDateStr": "2026-09-17T10:00:00",
        "Code": 90001,
        "Version": 1,
        "CodeVersion": code_version,
        "Status": 0,
        "Developers": [{"NkoName": "Профильная медицинская организация"}],
        "Mkbs": [{"MkbName": "Инфаркт мозга", "MkbCode": "I63"}],
    }


def test_minzdrav_sync_is_idempotent_and_public(client):
    external_id = "test-neuro-1"
    cleanup("minzdrav", external_id)
    with app.app_context():
        first = sync_minzdrav([minzdrav_item(external_id)])
        second = sync_minzdrav([minzdrav_item(external_id)])
        assert first["created"] == 1
        assert second["unchanged"] == 1
        assert ClinicalGuideline.query.filter_by(external_id=external_id).count() == 1

    page = client.get("/clinical-guidelines/?kind=russian&q=инсульт")
    assert page.status_code == 200
    assert "Ишемический инсульт".encode("utf-8") in page.data
    assert b"cr.minzdrav.gov.ru/view-cr/test-neuro-1" in page.data
    cleanup("minzdrav", external_id)


def test_external_import_accepts_only_official_domain():
    external_id = "aan-test-1"
    cleanup("aan", external_id)
    payload = {
        "source_key": "aan",
        "external_id": external_id,
        "title": "Practice guideline for a neurological condition",
        "url": "https://www.aan.com/practice/example-guideline",
        "published_on": "2026-09-17",
        "version": "1",
        "specialties": "Neurology",
    }
    with app.app_context():
        _record, action = upsert_guideline(payload)
        db.session.commit()
        assert action == "created"
        unsafe = {**payload, "external_id": "unsafe", "url": "https://example.com/file"}
        try:
            upsert_guideline(unsafe)
        except GuidelineValidationError as exc:
            assert "официальных источников" in str(exc)
        else:
            raise AssertionError("Неофициальный домен должен быть отклонён")
    cleanup("aan", external_id)


def test_sync_api_requires_token(client):
    original = app.config.get("GUIDELINES_SYNC_TOKEN")
    app.config["GUIDELINES_SYNC_TOKEN"] = "test-secret"
    try:
        response = client.post("/api/clinical-guidelines/import/", json={})
        assert response.status_code == 401
    finally:
        app.config["GUIDELINES_SYNC_TOKEN"] = original


def test_registry_populates_public_cards(tmp_path):
    external_id = "registry-neuro-2026-1"
    cleanup("minzdrav", external_id)
    registry = tmp_path / "clinical_guidelines.json"
    registry.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "items": [
                    {
                        "source_key": "minzdrav",
                        "external_id": external_id,
                        "title": "Клинические рекомендации по неврологии",
                        "organization": "Минздрав России",
                        "version": "2026",
                        "codes": "G40",
                        "specialties": "Неврология",
                        "url": f"https://cr.minzdrav.gov.ru/view-cr/{external_id}",
                        "published_on": "17.09.2026",
                        "status": "active",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    with app.app_context():
        stats = sync_guidelines_registry(registry)
        assert stats["created"] == 1
        assert stats["scanned"] == 1
    cleanup("minzdrav", external_id)
