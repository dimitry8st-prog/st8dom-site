"""Публичная библиотека методичек и брошюр портала ДИС.

Life-OS готовит и связывает знания, а этот каталог показывает только
проверенные публикации. Один материал описывается здесь один раз и затем
может отображаться в нескольких тематических представлениях.
"""

from __future__ import annotations


LIBRARY_CATEGORIES = [
    {
        "slug": "ai-architecture",
        "title": "AI и архитектура",
        "description": "Проектирование, модели, интеграции, пилоты и контроль качества AI-систем.",
    },
    {
        "slug": "business-sales",
        "title": "Бизнес и продажи",
        "description": "Продуктовое мышление, экономика проектов, маркетинг, продажи и аналитика рынка.",
    },
    {
        "slug": "law-safety",
        "title": "Право и безопасность",
        "description": "Правовые требования, персональные данные, ответственность и защита цифрового бренда.",
    },
    {
        "slug": "brand-content",
        "title": "Бренд и контент",
        "description": "Личный бренд, коммуникации и система экспертных материалов.",
    },
    {
        "slug": "teamwork",
        "title": "Командная работа",
        "description": "Роли, доверие, ответственность и взаимодействие человека с AI.",
    },
]


LIBRARY_ITEMS = [
    {
        "slug": "ai-law-brand-protection",
        "title": "Искусственный интеллект в правовом поле",
        "summary": "История AI, безопасное применение, российская и мировая практика, защита бренда ДИС.",
        "category": "law-safety",
        "kind": "Брошюра",
        "date": "17.09.2026",
        "file": "ai-law-brand-protection.docx",
        "status": "Опубликовано",
        "featured": True,
        "directions": ["ai"],
    },
    {
        "slug": "ai-solution-architecture",
        "title": "Проектирование и запуск AI-решений",
        "summary": "Путь от бизнес-задачи и архитектуры до RAG, MVP, контроля рисков и эксплуатации.",
        "category": "ai-architecture",
        "kind": "Методичка",
        "date": "27.08.2026",
        "file": "ai-solution-architecture.docx",
        "status": "Опубликовано",
        "featured": True,
        "directions": ["ai", "life-os"],
    },
    {
        "slug": "ai-model-evaluation",
        "title": "Оценка AI-моделей",
        "summary": "Практический выбор моделей по качеству, стоимости, скорости, рискам и сценарию применения.",
        "category": "ai-architecture",
        "kind": "Методичка",
        "date": "21.08.2026",
        "file": "ai-model-evaluation.docx",
        "status": "Опубликовано",
        "featured": True,
        "directions": ["ai", "life-os"],
    },
    {
        "slug": "autosfera-n8n-langflow",
        "title": "Интеграция n8n и Langflow в AutoSfera AI",
        "summary": "Оркестратор, независимые сценарии, единый обмен данными, ошибки и контроль оператора.",
        "category": "ai-architecture",
        "kind": "Методичка",
        "date": "27.08.2026",
        "file": "autosfera-n8n-langflow.docx",
        "status": "Опубликовано",
        "featured": False,
        "directions": ["ai"],
    },
    {
        "slug": "ai-launch-quality-handover",
        "title": "Запуск, контроль качества и передача AI-решений",
        "summary": "Методика от готовности к пилоту до промышленной эксплуатации и сопровождения.",
        "category": "ai-architecture",
        "kind": "Методичка",
        "date": "28.08.2026",
        "file": "ai-launch-quality-handover.docx",
        "status": "Опубликовано",
        "featured": False,
        "directions": ["ai"],
    },
    {
        "slug": "ai-learning-tool",
        "title": "AI как инструмент обучения",
        "summary": "Как использовать AI для объяснения, практики, проверки знаний и индивидуальной траектории.",
        "category": "ai-architecture",
        "kind": "Методичка",
        "date": "2026",
        "file": "ai-learning-tool.docx",
        "status": "Опубликовано",
        "featured": False,
        "directions": ["ai", "life-os"],
    },
    {
        "slug": "ai-audit-pilot",
        "title": "AI-аудит и пилотное внедрение",
        "summary": "Рабочая методика обследования процесса, выбора пилота и проверки результата.",
        "category": "ai-architecture",
        "kind": "Методика",
        "date": "25.08.2026",
        "file": None,
        "status": "На редактуре",
        "featured": False,
        "directions": ["ai"],
    },
    {
        "slug": "ai-project-economics",
        "title": "Экономическое обоснование и внедрение AI-проектов",
        "summary": "Эффект, TCO, риски, стейкхолдеры и условия перехода от пилота к эксплуатации.",
        "category": "business-sales",
        "kind": "Методичка",
        "date": "28.08.2026",
        "file": "ai-project-economics.docx",
        "status": "Опубликовано",
        "featured": True,
        "directions": ["ai"],
    },
    {
        "slug": "product-thinking-ai-it",
        "title": "Основы продуктового мышления в AI и IT",
        "summary": "Пользовательская проблема, ценность, гипотезы, MVP и измеримые критерии продукта.",
        "category": "business-sales",
        "kind": "Методичка",
        "date": "2026",
        "file": "product-thinking-ai-it.docx",
        "status": "Опубликовано",
        "featured": False,
        "directions": ["ai"],
    },
    {
        "slug": "system-sales",
        "title": "Системные продажи",
        "summary": "Практическая система работы с клиентом, предложением, возражениями и следующим шагом.",
        "category": "business-sales",
        "kind": "Методичка",
        "date": "2026",
        "file": "system-sales.docx",
        "status": "Опубликовано",
        "featured": False,
        "directions": [],
    },
    {
        "slug": "competitive-intelligence",
        "title": "Конкурентная разведка",
        "summary": "Поиск, проверка и применение открытой информации для продуктовых и бизнес-решений.",
        "category": "business-sales",
        "kind": "Методичка",
        "date": "17.08.2026",
        "file": "competitive-intelligence.docx",
        "status": "Опубликовано",
        "featured": False,
        "directions": ["ai"],
    },
    {
        "slug": "business-sales-letters",
        "title": "Деловые и продающие письма",
        "summary": "Структура понятного письма: задача клиента, предложение, доказательства и действие.",
        "category": "business-sales",
        "kind": "Методичка",
        "date": "24.08.2026",
        "file": "business-sales-letters.docx",
        "status": "Опубликовано",
        "featured": False,
        "directions": [],
    },
    {
        "slug": "neural-networks-marketing",
        "title": "Нейросети в маркетинге",
        "summary": "Практическая брошюра о применении AI в исследовании аудитории, контенте и продвижении.",
        "category": "business-sales",
        "kind": "Брошюра",
        "date": "21.08.2026",
        "file": "neural-networks-marketing.docx",
        "status": "Опубликовано",
        "featured": False,
        "directions": ["ai"],
    },
    {
        "slug": "personal-brand",
        "title": "Создание личного бренда",
        "summary": "Позиционирование, доказательства, линейка услуг и система сообщений специалиста.",
        "category": "brand-content",
        "kind": "Методичка",
        "date": "2026",
        "file": "personal-brand.docx",
        "status": "Опубликовано",
        "featured": True,
        "directions": [],
    },
    {
        "slug": "team-system",
        "title": "Команда как система",
        "summary": "Коммуникация, доверие и ответственность в эпоху искусственного интеллекта.",
        "category": "teamwork",
        "kind": "Методичка",
        "date": "01.09.2026",
        "file": "team-system.docx",
        "status": "Опубликовано",
        "featured": True,
        "directions": ["ai"],
    },
    {
        "slug": "teamwork",
        "title": "Командная работа",
        "summary": "Роли участников, правила взаимодействия и понятные критерии общего результата.",
        "category": "teamwork",
        "kind": "Методичка",
        "date": "13.08.2026",
        "file": "teamwork-13-08-2026.docx",
        "status": "Опубликовано",
        "featured": False,
        "directions": [],
    },
    {
        "slug": "effective-teamwork",
        "title": "Методика эффективной командной работы",
        "summary": "Практические инструменты распределения ответственности, обратной связи и контроля.",
        "category": "teamwork",
        "kind": "Методика",
        "date": "21.08.2026",
        "file": "effective-teamwork.docx",
        "status": "Опубликовано",
        "featured": False,
        "directions": [],
    },
]


def grouped_library_items(selected_category: str = "") -> list[dict]:
    """Возвращает непустые тематические блоки в стабильном порядке."""
    groups = []
    for category in LIBRARY_CATEGORIES:
        if selected_category and category["slug"] != selected_category:
            continue
        items = [item for item in LIBRARY_ITEMS if item["category"] == category["slug"]]
        if items:
            groups.append({**category, "items": items})
    return groups


def featured_library_items(limit: int = 6) -> list[dict]:
    return [item for item in LIBRARY_ITEMS if item["featured"]][:limit]


def library_items_for_direction(direction: str, limit: int = 6) -> list[dict]:
    return [item for item in LIBRARY_ITEMS if direction in item["directions"]][:limit]
