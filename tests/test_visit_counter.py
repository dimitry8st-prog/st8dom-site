"""Счётчик не удваивает визит при переходе между страницами."""

from app import app, visit_stats
from extensions import db
from models import AdminUser


def test_visits_are_deduplicated_and_visible_to_admin(client):
    with app.app_context():
        before = visit_stats()["total"]

    first = client.get("/")
    assert first.status_code == 200
    assert b"visit-counter" in first.data
    client.get("/cases/")
    with app.app_context():
        assert visit_stats()["total"] == before + 1

    bot = app.test_client()
    bot.get("/", headers={"User-Agent": "Googlebot"})
    with app.app_context():
        assert visit_stats()["total"] == before + 1

    second = app.test_client()
    second.get("/")
    with app.app_context():
        assert visit_stats()["total"] == before + 2
        admin_id = AdminUser.query.first().id
    with client.session_transaction() as session:
        session["_user_id"] = str(admin_id)
        session["_fresh"] = True
    dashboard = client.get("/admin/")
    assert dashboard.status_code == 200
    assert "Посещения портала" in dashboard.get_data(as_text=True)
    assert "За выбранный период:" in dashboard.get_data(as_text=True)
    future = client.get("/admin/?visits_from=2099-01-01&visits_to=2099-01-07")
    assert "За выбранный период: <strong>0</strong>" in future.get_data(as_text=True)
    invalid = client.get("/admin/?visits_from=2099-02-01&visits_to=2099-01-01")
    assert "Выберите даты по порядку" in invalid.get_data(as_text=True)
    with app.app_context():
        assert visit_stats()["total"] == before + 2
