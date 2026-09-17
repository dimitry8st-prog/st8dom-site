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
    assert b"/telegram/" in page.data
    assert "Telegram-бот готовится".encode("utf-8") in page.data


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


def test_assistant_finds_portal_topic():
    result = answer_question("найди нейрохирургию", {})
    assert result["escalated"] is False
    assert result["source"] == "portal"
    assert result["results"][0]["url"] == "/directions/medicine/neurology-neurosurgery/"


def test_assistant_finds_project_case():
    result = answer_question("Vitalis Medical AI", {})
    assert result["escalated"] is False
    assert any(item["url"] == "/cases/vitalis-medical-ai/" for item in result["results"])


def test_assistant_lists_brochures_instead_of_unrelated_case():
    result = answer_question("Какие брошюры есть?", {})
    assert result["escalated"] is False
    assert result["source"] == "library"
    assert "2 брошюры" in result["answer"]
    assert {item["url"] for item in result["results"]} == {
        "/library/#ai-law-brand-protection",
        "/library/#neural-networks-marketing",
    }
    assert all(item["kind"] == "Библиотека" for item in result["results"])


def test_assistant_finds_specific_brochure_by_topic():
    result = answer_question("Найди брошюру про защиту бренда", {})
    assert result["escalated"] is False
    assert result["source"] == "library"
    assert result["results"][0]["url"] == "/library/#ai-law-brand-protection"
    assert len(result["results"]) == 1


def test_assistant_lists_methodical_materials():
    result = answer_question("Какие методички есть?", {})
    assert result["escalated"] is False
    assert result["source"] == "library"
    assert "15 методических материалов" in result["answer"]
    assert result["results"]


def test_assistant_answers_brochure_count_question():
    result = answer_question("Сколько брошюр доступно?", {})
    assert result["source"] == "library"
    assert "2 брошюры" in result["answer"]


def test_chat_endpoint_returns_relevant_brochures(client):
    limiter.reset()
    response = client.post("/chat/", json={"message": "Какие брошюры есть?"})
    assert response.status_code == 200
    result = response.get_json()
    assert result["source"] == "library"
    assert [item["url"] for item in result["results"]] == [
        "/library/#ai-law-brand-protection",
        "/library/#neural-networks-marketing",
    ]


def test_assistant_finds_published_article(client):
    limiter.reset()
    response = client.post("/chat/", json={"message": "реабилитация после ишемического инсульта"})
    assert response.status_code == 200
    result = response.get_json()
    assert result["escalated"] is False
    assert any(
        item["url"] == "/materials/reabilitaciya-posle-ishemicheskogo-insulta/"
        for item in result["results"]
    )


def test_assistant_finds_term_inside_published_article(client):
    limiter.reset()
    response = client.post("/chat/", json={"message": "цитиколин"})
    result = response.get_json()
    assert result["escalated"] is False
    assert any(
        item["url"] == "/materials/reabilitaciya-posle-ishemicheskogo-insulta/"
        for item in result["results"]
    )


def test_offtopic_escalates():
    result = answer_question("как сварить борщ из свёклы?", {})
    assert result["escalated"] is True
    assert result["answer"] == ESCALATE_TEXT
    assert result["results"] == []


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
