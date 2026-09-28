"""Коммерческие продукты портала ДИС."""

PRODUCTS = [
    {
        "slug": "express-review",
        "name": "Экспресс-разбор",
        "price": 3900,
        "price_label": "3 900 ₽",
        "summary": "Разбор задачи, рекомендации и план следующих шагов.",
        "payment_object": "service",
        "sellable": True,
    },
    {
        "slug": "ai-audit",
        "name": "AI-аудит процесса",
        "price": 12900,
        "price_label": "12 900 ₽",
        "summary": "Разбор процесса, точки автоматизации, архитектура и дорожная карта.",
        "payment_object": "service",
        "sellable": True,
    },
    {
        "slug": "meeting-intelligence",
        "name": "Meeting Intelligence",
        "price": 14900,
        "price_label": "14 900 ₽",
        "summary": "Настройка рабочего контура для расшифровки встреч, решений и задач.",
        "payment_object": "service",
        "sellable": True,
    },
    {
        "slug": "reputation-assistant",
        "name": "Reputation Assistant",
        "price": 19900,
        "price_label": "19 900 ₽",
        "summary": "Анализ отзывов, проекты ответов и контроль человеком.",
        "payment_object": "service",
        "sellable": True,
    },
    {
        "slug": "knightcat-content-factory",
        "name": "KnightCat Content Factory",
        "price": 24900,
        "price_label": "24 900 ₽",
        "summary": "Контент-завод: идея → тексты → изображение → согласование → публикация.",
        "payment_object": "service",
        "sellable": True,
    },
    {
        "slug": "custom-ai",
        "name": "Custom AI / RAG",
        "price": None,
        "price_label": "Индивидуальный расчёт",
        "summary": "RAG, агенты, CRM, интеграции, базы данных и несколько каналов.",
        "payment_object": "service",
        "sellable": False,
    },
]

PRODUCTS_BY_SLUG = {item["slug"]: item for item in PRODUCTS}
