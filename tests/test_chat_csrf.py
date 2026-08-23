"""Виджет должен ходить в /chat/ с CSRF-токеном."""

import re

from app import app


def test_chat_accepts_csrf_header():
    previous = app.config["WTF_CSRF_ENABLED"]
    app.config["WTF_CSRF_ENABLED"] = True
    try:
        with app.test_client() as client:
            page = client.get("/")
            match = re.search(br'data-csrf="([^"]+)"', page.data)
            assert match, "нет CSRF в разметке виджета"
            token = match.group(1).decode("utf-8")

            denied = client.post("/chat/", json={"message": "Какие услуги вы оказываете?"})
            assert denied.status_code == 400

            ok = client.post(
                "/chat/",
                json={"message": "Какие услуги вы оказываете?"},
                headers={"X-CSRFToken": token},
            )
            assert ok.status_code == 200
            assert ok.get_json()["escalated"] is False
    finally:
        app.config["WTF_CSRF_ENABLED"] = previous
