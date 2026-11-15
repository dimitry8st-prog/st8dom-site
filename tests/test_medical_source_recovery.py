"""Temporary source failures must not block another source or erase old cards."""
import json
import sys

import pytest
import requests

import clinical_guidelines as guidelines
from scripts import sync_clinical_guidelines_vault as collector
from scripts.export_remote_clinical_guidelines import export_snapshot


def response(status=200, payload=None, text=None, url=guidelines.MINZDRAV_API_URL):
    result = requests.Response()
    result.status_code = status
    result.url = url
    result.encoding = "utf-8"
    result._content = (text if text is not None else json.dumps(payload)).encode()
    return result


def russian_item():
    return {
        "Name": "Мигрень", "NPC_approved": True, "CodeVersion": "recovery-1",
        "Version": 1, "Status": 0, "PublishDateStr": "2026-11-15",
        "Developers": [], "Mkbs": [{"MkbCode": "G43"}],
        "Specialities": [{"ReferenceName": "Неврология"}],
    }


def international_item():
    return {
        "source_key": "aao_hnsf",
        **guidelines.AAO_HNSF_WATCHED_GUIDELINES["cpg-tinnitus-update"],
        "published_on": "2026-10-12", "status": "active",
    }


@pytest.mark.parametrize("failure", [500, 503, 429, requests.ReadTimeout("test")])
def test_minzdrav_recovers_on_third_attempt_with_same_page(monkeypatch, failure):
    pauses, calls = [], []
    monkeypatch.setattr(guidelines.time, "sleep", pauses.append)

    def post(url, **kwargs):
        calls.append(kwargs)
        if len(calls) < 3:
            if isinstance(failure, Exception):
                raise failure
            return response(failure)
        return response(payload={"Data": [russian_item()], "TotalRecords": 1})

    data = guidelines.fetch_minzdrav_page(current_page=1, page_size=25, request_post=post)
    assert len(data["Data"]) == 1
    assert pauses == [1, 2]
    assert len(calls) == 3
    assert all(call["json"] == calls[0]["json"] for call in calls)
    assert calls[0]["json"]["pageSize"] == 25
    assert calls[0]["allow_redirects"] is False


@pytest.mark.parametrize("status,attempts", [(403, 1), (500, 3)])
def test_minzdrav_stops_after_bounded_failures(monkeypatch, status, attempts):
    monkeypatch.setattr(guidelines.time, "sleep", lambda _: None)
    calls = []

    def post(*args, **kwargs):
        calls.append(1)
        return response(status)

    with pytest.raises(requests.HTTPError):
        guidelines.fetch_minzdrav_page(request_post=post)
    assert len(calls) == attempts


@pytest.mark.parametrize("payload", [
    [], {}, {"Data": [None], "TotalRecords": 1},
    {"Data": [], "TotalRecords": 25}, {"Data": [], "TotalRecords": -1},
    {"Data": [], "TotalRecords": True},
])
def test_minzdrav_invalid_or_incomplete_page_is_not_success(payload):
    with pytest.raises(RuntimeError):
        guidelines.fetch_minzdrav_page(request_post=lambda *a, **kw: response(payload=payload))


def test_minzdrav_does_not_follow_api_redirect():
    with pytest.raises(guidelines.GuidelineValidationError):
        guidelines.fetch_minzdrav_page(request_post=lambda *a, **kw: response(302, payload={}))


def test_aao_layout_change_is_reported_instead_of_green_empty_collection():
    with pytest.raises(guidelines.GuidelineValidationError, match="каталог изменился"):
        guidelines.fetch_aao_hnsf_guidelines(request_get=lambda *a, **kw: response(
            text="<html>New catalogue layout</html>", url=guidelines.AAO_HNSF_GUIDELINES_URL,
        ))


def test_aao_recovers_from_transient_failure(monkeypatch):
    monkeypatch.setattr(guidelines.time, "sleep", lambda _: None)
    calls = []

    def get(*args, **kwargs):
        calls.append(1)
        return response(
            503 if len(calls) == 1 else 200,
            text='''<a href="/cpg-tinnitus-update/">Tinnitus Update</a>
                Clinical Practice Guideline: Tinnitus Update published in
                Otolaryngology-Head and Neck Surgery on October 12, 2026.''',
            url=guidelines.AAO_HNSF_GUIDELINES_URL,
        )

    assert guidelines.fetch_aao_hnsf_guidelines(request_get=get) == [international_item()]
    assert len(calls) == 2


@pytest.fixture
def registry(monkeypatch, tmp_path):
    path = tmp_path / "registry.json"
    monkeypatch.setattr(collector, "REGISTRY_PATH", path)
    monkeypatch.setattr(collector, "VAULT_DIR", tmp_path / "vault")
    old = guidelines._minzdrav_payload({**russian_item(), "CodeVersion": "old-1"})
    path.write_text(json.dumps({"items": [old]}, ensure_ascii=False))
    return path


def fail_minzdrav(**kwargs):
    raise requests.HTTPError("body must not enter report", response=response(500))


def test_russian_outage_still_saves_international_and_repeat_does_not_duplicate(monkeypatch, registry):
    monkeypatch.setattr(collector, "fetch_minzdrav_page", fail_minzdrav)
    monkeypatch.setattr(collector, "fetch_aao_hnsf_guidelines", lambda: [international_item()])
    result = collector.sync(5)
    assert result["ok"] is False
    assert result["errors"] == ["minzdrav: HTTP 500"]
    assert result["sources"]["aao_hnsf"]["ok"] is True
    assert result["stored"] == 2
    original = registry.read_text()
    assert collector.sync(5)["stored"] == 2
    assert registry.read_text() == original
    assert {row["external_id"] for row in json.loads(original)["items"]} == {
        "old-1", "AAO-HNSF-TINNITUS-UPDATE-2026",
    }


def test_failed_second_page_does_not_commit_partial_source(monkeypatch, registry):
    def page(**kwargs):
        if kwargs["current_page"] == 1:
            return {"Data": [russian_item()], "TotalRecords": 100}
        raise requests.ReadTimeout("test")

    monkeypatch.setattr(collector, "fetch_minzdrav_page", page)
    monkeypatch.setattr(collector, "fetch_aao_hnsf_guidelines", lambda: [international_item()])
    result = collector.sync(5)
    ids = {row["external_id"] for row in json.loads(registry.read_text())["items"]}
    assert result["sources"]["minzdrav"]["ok"] is False
    assert "recovery-1" not in ids
    assert "old-1" in ids and international_item()["external_id"] in ids


def test_international_outage_still_saves_russian_source(monkeypatch, registry):
    monkeypatch.setattr(collector, "fetch_minzdrav_page", lambda **kw: {
        "Data": [russian_item()], "TotalRecords": 1,
    })

    def fail():
        raise guidelines.GuidelineValidationError("layout changed")

    monkeypatch.setattr(collector, "fetch_aao_hnsf_guidelines", fail)
    result = collector.sync(5)
    assert result["ok"] is False
    assert result["sources"]["minzdrav"]["ok"] is True
    assert result["stored"] == 2
    assert result["errors"] == ["aao_hnsf: GuidelineValidationError"]


def test_command_persists_report_and_fails_when_both_sources_unavailable(monkeypatch, registry, tmp_path, capsys):
    monkeypatch.setattr(collector, "fetch_minzdrav_page", fail_minzdrav)
    def fail():
        raise requests.ReadTimeout("private text")
    monkeypatch.setattr(collector, "fetch_aao_hnsf_guidelines", fail)
    report = tmp_path / "report.json"
    monkeypatch.setattr(sys, "argv", ["sync", "--report-file", str(report)])
    with pytest.raises(SystemExit) as error:
        collector.main()
    assert error.value.code == 1
    data = json.loads(report.read_text())
    assert data["stored"] == 1
    assert data["ok"] is False
    assert len(data["errors"]) == 2
    assert "checked_at" in data
    assert "private text" not in capsys.readouterr().out


def test_successful_sources_produce_ok_report(monkeypatch, registry):
    monkeypatch.setattr(collector, "fetch_minzdrav_page", lambda **kw: {
        "Data": [russian_item()], "TotalRecords": 1,
    })
    monkeypatch.setattr(collector, "fetch_aao_hnsf_guidelines", lambda: [international_item()])
    result = collector.sync(5)
    assert result["ok"] is True and result["errors"] == []
    assert result["stored"] == 3


def test_remote_snapshot_does_not_change_original_registry_or_notes(monkeypatch, registry):
    original = registry.read_text()
    vault = collector.VAULT_DIR
    vault.mkdir()
    note = vault / "my-note.md"
    note.write_text("Reviewed personal notes")
    monkeypatch.setattr(collector, "fetch_minzdrav_page", lambda **kw: {
        "Data": [russian_item()], "TotalRecords": 1,
    })
    monkeypatch.setattr(collector, "fetch_aao_hnsf_guidelines", lambda: [international_item()])
    snapshot = export_snapshot()
    assert registry.read_text() == original
    assert note.read_text() == "Reviewed personal notes"
    assert collector.REGISTRY_PATH == registry and collector.VAULT_DIR == vault
    assert snapshot["result"]["ok"] is True
    assert {row["external_id"] for row in snapshot["items"]} == {
        "recovery-1", international_item()["external_id"],
    }


def test_snapshot_merge_preserves_existing_cards_after_partial_remote_failure(monkeypatch, registry, tmp_path):
    monkeypatch.setattr(collector, "fetch_minzdrav_page", fail_minzdrav)
    monkeypatch.setattr(collector, "fetch_aao_hnsf_guidelines", lambda: [international_item()])
    snapshot = export_snapshot()
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(snapshot))
    result = collector.apply_snapshot(path)
    assert result["stored"] == 2 and result["ok"] is False
    assert result["collection_location"] == "portal-vps"
    assert collector.apply_snapshot(path)["stored"] == 2
    assert {row["external_id"] for row in json.loads(registry.read_text())["items"]} == {
        "old-1", international_item()["external_id"],
    }


@pytest.mark.parametrize("change", ["url", "source", "status", "shape"])
def test_snapshot_rejects_untrusted_or_inconsistent_data_before_writing(registry, tmp_path, change):
    original = registry.read_text()
    snapshot = {
        "schema_version": 1,
        "result": {"ok": True, "errors": [], "sources": {
            "minzdrav": {"ok": True}, "aao_hnsf": {"ok": True},
        }},
        "items": [international_item()],
    }
    if change == "url":
        snapshot["items"][0]["url"] = "https://example.org/untrusted"
    elif change == "source":
        snapshot["items"][0]["source_key"] = "unknown"
    elif change == "status":
        snapshot["result"]["sources"]["aao_hnsf"]["ok"] = False
    else:
        snapshot["items"] = None
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(snapshot))
    with pytest.raises(ValueError):
        collector.apply_snapshot(path)
    assert registry.read_text() == original
