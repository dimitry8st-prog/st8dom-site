"""Дымовые проверки маршрутов, формы и админки."""

from app import app
from models import Inquiry


def test_home_ok(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Обсудить задачу".encode("utf-8") in response.data
    assert "Выбрать направление".encode("utf-8") in response.data
    assert "Медицина, AI и будущее человека".encode("utf-8") in response.data
    assert "Дмитрий Степанов".encode("utf-8") in response.data
    assert b'class="author-details"' in response.data
    assert ">Подробнее<".encode("utf-8") in response.data
    assert "Сначала работал нейрохирургом".encode("utf-8") in response.data
    assert "юридическое и экономическое образование".encode("utf-8") in response.data
    assert "По мере развития портала этот раздел".encode("utf-8") not in response.data
    assert "от 15 000".encode("utf-8") in response.data
    assert "от 180 000".encode("utf-8") in response.data
    assert b"dis-mascot-orange.jpg" in response.data
    assert b"t.me/Dmitryprompt" not in response.data
    assert b"/telegram/" in response.data
    assert "Telegram-бот готовится".encode("utf-8") in response.data
    assert b'id="chat-launcher"' in response.data


def test_cases_and_details(client):
    listing = client.get("/cases/")
    assert listing.status_code == 200
    slugs = [
        "autosfera-ai",
        "vitalis-medical-ai",
        "healthy-store",
        "dis-reputatsiya-360",
        "legalbot",
        "docpulse",
        "ai-nastavnik-360",
        "dis-analyst-360",
        "faq-assistant",
        "telegram-bot",
        "online-store-ops",
        "crm-automation",
        "corporate-site",
        "ai-support",
        "redcat-ai",
        "meeting-360",
        "lingua-360",
        "onboardflow-ai",
    ]
    for slug in slugs:
        page = client.get(f"/cases/{slug}/")
        assert page.status_code == 200, slug
        assert "Репозиторий".encode("utf-8") in page.data

    autosfera = client.get("/cases/autosfera-ai/")
    assert b"AutoSfera-AI-" in autosfera.data
    assert "18 зарегистрированных skills".encode("utf-8") in autosfera.data
    assert "контролируемая beta".encode("utf-8") in autosfera.data

    vitalis = client.get("/cases/vitalis-medical-ai/")
    assert b"Vitalis-Medical-AI" in vitalis.data
    assert b"vitalis-medical-ai.mp4" in vitalis.data
    assert b"Vitalis-Medical-AI-FL.png" in vitalis.data
    assert "не медицинское изделие".encode("utf-8") in vitalis.data

    healthy_store = client.get("/cases/healthy-store/")
    assert b"Zdorowii_magazin" in healthy_store.data
    assert "концепция / техническое задание".encode("utf-8") in healthy_store.data
    assert b"case-healthy-store.webp" in healthy_store.data
    assert b"biobalance-promo-16x9.mp4" in healthy_store.data
    assert b"biobalance-promo-poster.webp" in healthy_store.data
    assert b"biobalance-promo-ru.vtt" in healthy_store.data
    assert b'preload="metadata"' in healthy_store.data
    assert b"case-autosfera-ai.png" in autosfera.data
    assert b"autosfera-ai-defense.mp4" in autosfera.data
    assert b"autosfera-ai-defense-poster.png" in autosfera.data

    reputatsiya = client.get("/cases/dis-reputatsiya-360/")
    assert b"-_-360" in reputatsiya.data
    assert b"dis-reputatsiya-360-16x9.mp4" in reputatsiya.data
    assert "не служба репутации".encode("utf-8") in reputatsiya.data

    legalbot = client.get("/cases/legalbot/")
    assert b"JustBot" in legalbot.data
    assert b"legalbot-demo.mp4" in legalbot.data
    assert "не замена юриста".encode("utf-8") in legalbot.data

    docpulse = client.get("/cases/docpulse/")
    assert b"DocPulse" in docpulse.data
    assert b"docpulse-demo.mp4" in docpulse.data
    assert "не замена врача".encode("utf-8") in docpulse.data

    mentor = client.get("/cases/ai-nastavnik-360/")
    assert b"-AI--360" in mentor.data
    assert b"ai-nastavnik-360-16x9.mp4" in mentor.data
    assert b"ai-nastavnik-360-ru.vtt" in mentor.data
    assert "кадровые решения".encode("utf-8") in mentor.data

    analyst = client.get("/cases/dis-analyst-360/")
    assert b"-360" in analyst.data
    assert b"dis-analyst-360-16x9.mp4" in analyst.data
    assert b"dis-analyst-360-ru.vtt" in analyst.data
    assert "не облачная BI".encode("utf-8") in analyst.data

    faq = client.get("/cases/faq-assistant/")
    assert faq.status_code == 200
    assert b"Faq_assistants" in faq.data
    assert "Обсудить внедрение".encode("utf-8") in faq.data
    assert "Текстовая расшифровка ролика".encode("utf-8") in faq.data
    assert b"faq-assistant-poster.webp" in faq.data
    assert b"faq-assistant-ru.vtt" in faq.data
    assert b"faq-assistant-vo.mp3" in faq.data
    assert 'aria-label="Воспроизвести ролик"'.encode("utf-8") in faq.data
    assert b'preload="none"' in faq.data
    assert b"faq-assistant-demo.mp4" not in faq.data
    assert b"autoplay" not in faq.data.lower()


def test_portal_directions(client):
    expected = {
        "medicine": "Медицина",
        "ai": "AI на практике",
        "longevity": "Долголетие и будущее человека",
        "life-os": "Life-OS",
    }
    for slug, title in expected.items():
        page = client.get(f"/directions/{slug}/")
        assert page.status_code == 200, slug
        assert title.encode("utf-8") in page.data
        assert "Как проверяются материалы".encode("utf-8") in page.data

    assert client.get("/directions/unknown/").status_code == 404


def test_selected_projects_catalog(client):
    page = client.get("/projects/")
    assert page.status_code == 200
    assert "15 проектов".encode("utf-8") in page.data
    assert page.data.count(b'class="portal-project-card') == 15
    assert b"st8dom-site" not in page.data
    for name in [
        "AutoSfera-AI",
        "Vitalis Medical AI",
        "Life-OS",
        "DIS-Meeting-360",
        "MedBot-AI",
        "SAR-GPT-Analyzer",
        "OnboardFlow-AI",
    ]:
        assert name.encode("utf-8") in page.data
    assert page.data.count(b"project-video-trigger") == 8
    assert b"autosfera-ai-defense.mp4" in page.data
    assert b"dis-reputatsiya-360-16x9.mp4" in page.data
    assert b"ai-nastavnik-360-16x9.mp4" in page.data
    assert b"dis-analyst-360-16x9.mp4" in page.data
    assert b"docpulse-demo.mp4" in page.data
    assert b"legalbot-demo.mp4" in page.data
    assert b"biobalance-promo-16x9.mp4" in page.data
    assert b"vitalis-medical-ai.mp4" in page.data
    assert b"Vitalis-Medical-AI-FL.png" in page.data
    html = page.data.decode("utf-8")
    vitalis_start = html.index("<h2>Vitalis Medical AI</h2>")
    vitalis_end = html.index("</article>", vitalis_start)
    vitalis_card = html[vitalis_start:vitalis_end]
    assert vitalis_card.count('class="btn ') == 2
    assert "Смотреть видео" in vitalis_card
    assert "Подробнее" in vitalis_card
    assert "GitHub" not in vitalis_card
    assert b'id="project-video-modal"' in page.data
    assert b"portfolio_repo_open" not in page.data
    assert "Репозиторий готовится к публикации".encode("utf-8") in page.data


def test_legal_and_seo(client):
    assert client.get("/privacy/").status_code == 200
    assert client.get("/consent/").status_code == 200
    robots = client.get("/robots.txt")
    assert robots.status_code == 200
    assert b"Sitemap" in robots.data
    sitemap = client.get("/sitemap.xml")
    assert sitemap.status_code == 200
    assert b"/cases/faq-assistant/" in sitemap.data
    assert b"/cases/ai-nastavnik-360/" in sitemap.data
    assert b"/cases/dis-analyst-360/" in sitemap.data
    assert b"/cases/dis-reputatsiya-360/" in sitemap.data
    assert b"/cases/autosfera-ai/" in sitemap.data
    assert b"/cases/vitalis-medical-ai/" in sitemap.data
    assert b"/cases/healthy-store/" in sitemap.data
    assert b"/projects/" in sitemap.data
    assert b"/directions/medicine/" in sitemap.data
    assert b"/directions/ai/" in sitemap.data
    assert b"/directions/longevity/" in sitemap.data
    assert b"/directions/life-os/" in sitemap.data
    assert client.get("/no-such-page/").status_code == 404


def test_contact_prefills_faq_topic(client):
    page = client.get("/contact/?topic=faq")
    assert page.status_code == 200
    assert 'value="faq" selected'.encode("utf-8") in page.data or b'value="faq"' in page.data


def test_contact_prefills_express_topic(client):
    page = client.get("/contact/?topic=express")
    assert page.status_code == 200
    assert b'value="express"' in page.data


def test_contact_validation_and_save(client):
    bad = client.post("/contact/", data={"name": "А"}, follow_redirects=True)
    assert bad.status_code == 200

    ok = client.post(
        "/contact/",
        data={
            "name": "Иван Петров",
            "email": "ivan@example.com",
            "phone": "+7 900 000-00-00",
            "topic": "audit",
            "message": "Нужно разобрать процесс поддержки и собрать MVP.",
            "consent": "y",
        },
        follow_redirects=True,
    )
    assert ok.status_code == 200
    assert (
        "Заявка отправлена".encode("utf-8") in ok.data
        or "Заявка сохранена".encode("utf-8") in ok.data
    )
    with app.app_context():
        saved = Inquiry.query.filter_by(email="ivan@example.com").first()
        assert saved is not None


def test_admin_requires_login(client):
    response = client.get("/admin/", follow_redirects=True)
    assert response.status_code == 200
    assert "Панель заявок".encode("utf-8") in response.data
