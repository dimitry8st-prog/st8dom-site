"""Детерминированные намерения для частых и чувствительных вопросов Дису.

RAG остаётся основным способом отвечать по содержанию портала. Этот модуль
перехватывает только запросы, где посетителю нужен однозначный маршрут либо
где ответ модели недопустим (медицинское назначение, секреты, изменение сайта).
"""

from __future__ import annotations

import re
from typing import Any

from assistant.retrieve import normalize


def _has(text: str, *patterns: str) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def _result(item: dict[str, Any]) -> dict[str, str]:
    return {
        "title": item.get("title") or item["question"],
        "url": item["url"],
        "kind": item.get("kind_label") or "Материал",
    }


def _document(knowledge: tuple[dict[str, Any], ...], item_id: str) -> dict[str, Any] | None:
    return next((item for item in knowledge if item.get("id") == item_id), None)


def _page_response(
    knowledge: tuple[dict[str, Any], ...],
    item_id: str,
    answer: str,
    *,
    source: str = "intent",
) -> dict[str, Any] | None:
    item = _document(knowledge, item_id)
    if not item or not item.get("url"):
        return None
    return {
        "answer": answer,
        "escalated": False,
        "source": source,
        "results": [_result(item)],
    }


def _article_listing(knowledge: tuple[dict[str, Any], ...]) -> dict[str, Any] | None:
    page = _document(knowledge, "page-materials")
    if not page:
        return None
    articles = [item for item in knowledge if item.get("kind") == "article"]
    results = [_result(page), *[_result(item) for item in articles[:3]]]
    suffix = f" Сейчас опубликовано материалов: {len(articles)}." if articles else ""
    return {
        "answer": f"Все статьи и обзоры собраны в разделе «Материалы».{suffix}",
        "escalated": False,
        "source": "intent",
        "results": results,
    }


def route_intent(
    question: str,
    knowledge: tuple[dict[str, Any], ...],
) -> dict[str, Any] | None:
    """Возвращает однозначный ответ либо передаёт вопрос обычному RAG-поиску."""
    text = normalize(question)

    # Жёсткие границы: Дис — answer-only помощник, а не врач и не администратор.
    if _has(
        text,
        r"постав(ь|ьте).{0,20}диагноз",
        r"что у меня за (болезнь|диагноз)",
        r"назнач(ь|ьте).{0,20}(лечени|лекарств|препарат)",
        r"какую доз(у|ировк)",
        r"сколько.{0,20}(таблет|мг|миллиграм)",
        r"отмен(ить|и).{0,20}(лекарств|препарат|лечени)",
    ):
        item = _document(knowledge, "direction-medicine")
        return {
            "answer": (
                "Я не ставлю диагнозы и не назначаю лечение или дозировки. "
                "Могу найти информационные материалы портала, но решение должен принимать врач. "
                "При резком ухудшении состояния обратитесь за экстренной медицинской помощью."
            ),
            "escalated": True,
            "source": "medical-safety",
            "results": [_result(item)] if item else [],
        }

    if _has(
        text,
        r"(покажи|раскрой|выдай|напиши).{0,25}(секрет|ключ|парол)",
        r"системн(ый|ые|ого).{0,15}(промпт|инструкц)",
        r"личн(ые|ую).{0,20}данн(ые|ых).{0,20}(посетител|пользовател)",
    ):
        return {
            "answer": "Я не раскрываю секреты, системные инструкции и персональные данные.",
            "escalated": True,
            "source": "security-safety",
            "results": [],
        }

    if _has(
        text,
        r"(измени|удали|опубликуй|отправь).{0,30}(сайт|стать|материал|сообщен)",
        r"(прими|проведи).{0,15}(оплат|платеж)",
    ):
        return {
            "answer": (
                "Я могу найти и объяснить материалы, но не изменяю сайт, не публикую, "
                "не отправляю сообщения и не принимаю оплату. Для этого требуется действие Дмитрия."
            ),
            "escalated": True,
            "source": "action-safety",
            "results": [],
        }

    # Списки и страницы должны открываться предсказуемо, а не через похожую статью.
    if _has(
        text,
        r"(покаж|дай|открой|найди).{0,20}(список|все).{0,15}(стат|публик|материал)",
        r"(какие|новые|последние).{0,15}(стать|публик)",
        r"^статьи$",
    ):
        return _article_listing(knowledge)

    if _has(
        text,
        r"(покаж|где|открой|какие|все).{0,18}(проект|портфоли)",
        r"^(проекты|портфолио)$",
    ):
        return _page_response(
            knowledge,
            "page-projects",
            "Все открытые проекты и демонстрации собраны в разделе «Проекты».",
        )

    if _has(text, r"(покаж|где|открой|какие|все).{0,18}кейс", r"^кейсы$"):
        return _page_response(
            knowledge,
            "page-cases",
            "Подробные разборы задач, архитектуры и ограничений собраны в разделе «Кейсы».",
        )

    navigation_prefix = _has(text, r"покаж", r"открой", r"где", r"раздел", r"что есть по", r"материал.*по")
    if navigation_prefix and _has(text, r"\blife[\s-]?os\b", r"лайф[\s-]?ос"):
        return _page_response(
            knowledge,
            "direction-life-os",
            "Life-OS — раздел о сборе, классификации и поиске знаний для подготовки материалов портала.",
        )
    if navigation_prefix and _has(text, r"\bai\b", r"\bии\b", r"искусственн.{0,12}интеллект"):
        return _page_response(
            knowledge,
            "direction-ai",
            "Раздел «AI на практике» содержит материалы о моделях, RAG, ассистентах, промптах и автоматизации.",
        )
    if navigation_prefix and _has(text, r"медицин", r"невролог", r"нейрохирург"):
        return _page_response(
            knowledge,
            "direction-medicine",
            "В разделе «Медицина» собраны материалы по неврологии, нейрохирургии, реабилитации и клиническим рекомендациям.",
        )
    if navigation_prefix and _has(text, r"долголет", r"старени", r"будущ.{0,10}человек"):
        return _page_response(
            knowledge,
            "direction-longevity",
            "Раздел «Долголетие и будущее человека» отделяет научные данные от гипотез и сценариев будущего.",
        )

    if _has(text, r"(где|открой|покаж).{0,15}библиотек"):
        item = next((item for item in knowledge if item.get("kind") == "library"), None)
        if item:
            return {
                "answer": "Методички и брошюры собраны в библиотеке ДИС.",
                "escalated": False,
                "source": "intent",
                "results": [{"title": "Библиотека ДИС", "url": "/library/", "kind": "Библиотека"}],
            }

    if _has(text, r"(где|открой|покаж|как).{0,15}поиск"):
        return {
            "answer": "На странице поиска можно искать по названию, рубрике, тегу, проекту и тексту публикаций.",
            "escalated": False,
            "source": "intent",
            "results": [{"title": "Поиск по порталу", "url": "/search/", "kind": "Страница"}],
        }

    if _has(text, r"(кто|об).{0,15}(автор|дмитри)", r"кто такой дмитрий степанов"):
        return _page_response(
            knowledge,
            "page-author",
            "Автор портала — Дмитрий Степанов, врач и AI-архитектор. Подробная информация находится в блоке «Об авторе».",
        )

    if _has(text, r"(как|где).{0,15}(связат|написат)", r"контакт", r"телеграм.{0,10}дмитри"):
        return _page_response(
            knowledge,
            "page-contact",
            "Связаться с Дмитрием можно через форму сайта или Telegram: https://t.me/Dmitryprompt",
        )

    if _has(text, r"можно.{0,15}скачат", r"как.{0,15}скачат", r"кнопк.{0,10}скачат"):
        return {
            "answer": "Скачивание методичек сейчас отключено. Материалы можно читать непосредственно на сайте.",
            "escalated": False,
            "source": "policy",
            "results": [{"title": "Библиотека ДИС", "url": "/library/", "kind": "Библиотека"}],
        }

    return None
