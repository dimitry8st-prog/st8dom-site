import pytest

from app import app
from extensions import db
from models import LifeOSMaterial


@pytest.fixture()
def ingest(client, monkeypatch):
    monkeypatch.setitem(app.config, "LIFEOS_INGEST_TOKEN", "test-ingest-key")
    headers = {"Authorization": "Bearer test-ingest-key"}
    with app.app_context():
        LifeOSMaterial.query.filter(LifeOSMaterial.source_url.like("https://news.mit.edu/test-ingest-%")).delete()
        db.session.commit()
    yield client, headers
    with app.app_context():
        LifeOSMaterial.query.filter(LifeOSMaterial.source_url.like("https://news.mit.edu/test-ingest-%")).delete()
        db.session.commit()


def record():
    return dict(title="Brain research", source_url="https://news.mit.edu/test-ingest-1?utm_source=rss", summary="Short summary", stream="science-neuro")


def test_ingest_auth_is_separate_from_reader(client, monkeypatch):
    monkeypatch.setitem(app.config, "LIFEOS_INGEST_TOKEN", "")
    assert client.post("/api/life-os/mit/import/", json={"materials": []}).status_code == 503
    monkeypatch.setitem(app.config, "LIFEOS_INGEST_TOKEN", "key")
    assert client.post("/api/life-os/mit/import/", json={"materials": []}).status_code == 401
    assert client.get("/api/life-os/mit/pending/").status_code == 401


def test_import_replay_pending_and_ack(ingest):
    client, headers = ingest
    response = client.post("/api/life-os/mit/import/", headers=headers, json={"materials": [record()]})
    assert response.json == {"ok": True, "created": 1, "existing": 0}
    assert response.headers["Cache-Control"] == "no-store"
    replay = client.post("/api/life-os/mit/import/", headers=headers, json={"materials": [record()]})
    assert replay.json["existing"] == 1
    pending = client.get("/api/life-os/mit/pending/", headers=headers).json["reports"]
    report = next(row for row in pending if row["title"] == "Brain research")
    assert set(report) == {"id", "title", "report", "portal_url"}
    assert report["report"] == "Short summary"
    url = f'/api/life-os/mit/reports/{report["id"]}/ack/'
    assert client.post(url, headers=headers, json={"notion_page_id": "bad"}).status_code == 400
    page = {"notion_page_id": "aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa"}
    for _ in range(2):
        assert client.post(url, headers=headers, json=page).status_code == 200
    assert client.post(url, headers=headers, json={"notion_page_id": "bbbbbbbb-bbbb-4bbb-bbbb-bbbbbbbbbbbb"}).status_code == 409
    assert not any(row["id"] == report["id"] for row in client.get("/api/life-os/mit/pending/", headers=headers).json["reports"])


@pytest.mark.parametrize("bad", [None, [], {"materials": [None]}, {"materials": [{**record(), "source_url": "https://evil.example/"}]}, {"materials": [{**record(), "stream": "security"}]}, {"materials": [{**record(), "title": 42}]}])
def test_invalid_batch_does_not_partially_import(ingest, bad):
    client, headers = ingest
    if isinstance(bad, dict):
        bad["materials"].insert(0, record())
    response = client.post("/api/life-os/mit/import/", headers=headers, json=bad)
    assert response.status_code == 400
    with app.app_context():
        assert LifeOSMaterial.query.filter_by(source_url="https://news.mit.edu/test-ingest-1").first() is None
