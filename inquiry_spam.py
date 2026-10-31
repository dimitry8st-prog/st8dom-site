"""Консервативный фильтр: язык, имя и почтовый провайдер не признаки спама."""

import re
import unicodedata


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "").casefold()
    return " ".join(
        "".join(
            char if char.isalnum() else " "
            for char in text
            if not unicodedata.category(char).startswith(("M", "C"))
        ).split()
    )


# Подтверждённый пользователем шаблон. Сравниваем весь текст, чтобы
# конкретный запрос на греческом о проекте/лечении не попал под фильтр.
_PRICE_TEMPLATE = _normalize("Γεια σου, ήθελα να μάθω την τιμή σας.")


def content_spam_reason(message: str) -> str | None:
    if _normalize(message) == _PRICE_TEMPLATE:
        return "known_price_template"
    # Несколько ссылок сами по себе допустимы: карантин только при
    # сочетании с характерным предложением рекламного продвижения.
    links = re.findall(r"(?:https?://|www\.)[^\s<>]+", message, re.I)
    normalized = _normalize(message)
    if len(links) >= 3 and any(
        phrase in normalized
        for phrase in ("buy backlinks", "seo promotion", "купить ссылки", "продвижение сайта")
    ):
        return "bulk_link_promotion"
    return None
