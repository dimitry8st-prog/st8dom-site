"""Проверки виджета FAQ: поиск, эскалация и эндпоинт /chat/."""

from assistant.answer import ESCALATE_TEXT, answer_question
from assistant.rate_limit import limiter


def test_home_has_widget(client):
    page = client.get("/")
    assert page.status_code == 200
    assert b'id="site-chat"' in page.data
    assert b"chat-widget.js" in page.data
    assert b"dis-mascot-orange.jpg" in page.data
    assert "Дис — цифровой помощник".encode("utf-8") in page.data
    assert b"t.me/+VNBg4iudNxw2Mzgy" in page.data


def test_admin_hides_widget(client):
    login = client.get("/admin/login/")
    assert login.status_code == 200
    assert b'id="site-chat"' not in login.data
    assert b"chat-widget.js" not in login.data


def test_known_question_from_faq():
    result = answer_question("С чего начинается работа?", {})
    assert result["escalated"] is False
    assert result["source"] == "faq"
    assert "диагностики" in result["answer"].lower()


def test_price_question_from_faq():
    result = answer_question("сколько стоит mvp?", {})
    assert result["escalated"] is False
    assert "15 000" in result["answer"]
    assert "оферт" in result["answer"].lower()


def test_dis_identity_from_faq():
    result = answer_question("кто такой дис?", {})
    assert result["escalated"] is False
    assert "дис" in result["answer"].lower()
    assert "помощник" in result["answer"].lower()


def test_offtopic_escalates():
    result = answer_question("как сварить борщ из свёклы?", {})
    assert result["escalated"] is True
    assert result["answer"] == ESCALATE_TEXT


def test_chat_endpoint_faq_and_escalate(client):
    limiter.reset()
    ok = client.post("/chat/", json={"message": "Какие услуги вы оказываете?"})
    assert ok.status_code == 200
    body = ok.get_json()
    assert body["escalated"] is False
    assert "telegram" in body["answer"].lower() or "услуг" in body["answer"].lower()

    miss = client.post("/chat/", json={"message": "какой сегодня курс доллара?"})
    assert miss.status_code == 200
    missed = miss.get_json()
    assert missed["escalated"] is True
    assert "заявку" in missed["answer"].lower()


def test_chat_empty_message(client):
    limiter.reset()
    response = client.post("/chat/", json={"message": "   "})
    assert response.status_code == 200
    assert response.get_json()["source"] == "empty"
