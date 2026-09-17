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
        "summary": "Помогает проверить AI-проект на правовые риски, безопасно работать с данными и защитить цифровой бренд.",
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
        "summary": "Пошагово проводит от бизнес-задачи и архитектуры до RAG, MVP, управления рисками и запуска в эксплуатацию.",
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
        "summary": "Даёт систему сравнения и выбора AI-моделей по качеству, стоимости, скорости, рискам и реальной задаче.",
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
        "summary": "Показывает, как связать n8n, Langflow и AutoSfera AI через единый обмен данными, проверки и контроль оператора.",
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
        "summary": "Помогает подготовить пилот, измерить качество, безопасно запустить AI-систему и передать её в сопровождение.",
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
        "summary": "Учит использовать AI как наставника: для диагностики, объяснения, практики, проверки знаний и повторения.",
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
        "summary": "Помогает обследовать рабочий процесс, выбрать задачу для первого пилота и заранее определить критерии успеха.",
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
        "summary": "Помогает рассчитать TCO, ROI и окупаемость, обосновать ценность проекта и принять решение о масштабировании.",
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
        "summary": "Учит начинать с проблемы пользователя, проверять гипотезы через MVP и измерять результат продукта.",
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
        "summary": "Помогает выстроить повторные продажи, реактивацию клиентов и работу с CRM без увеличения рекламного бюджета.",
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
        "summary": "Показывает, как находить и проверять данные о рынке, сравнивать конкурентов и выявлять свободные ниши.",
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
        "summary": "Даёт алгоритм ясного письма: понять задачу клиента, сформулировать предложение, доказательства и следующий шаг.",
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
        "summary": "Показывает, как применять AI для изучения аудитории, производства контента, продвижения и оценки результата.",
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
        "summary": "Помогает определить позиционирование, собрать доказательства экспертности и выстроить систему контента и услуг.",
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
        "summary": "Помогает распределить роли человека и AI, наладить доверие, фиксировать решения и отвечать за общий результат.",
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
        "summary": "Учит превращать размытые запросы в ясные задачи с ответственными, сроками, зависимостями и критериями готовности.",
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
        "summary": "Даёт готовые ритуалы, шаблоны задач, правила обратной связи, документации и контроля командной работы.",
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


def get_library_item(slug: str) -> dict | None:
    """Находит один материал библиотеки по публичному адресу."""
    return next((item for item in LIBRARY_ITEMS if item["slug"] == slug), None)


def featured_library_items(limit: int = 6) -> list[dict]:
    return [item for item in LIBRARY_ITEMS if item["featured"]][:limit]


def library_items_for_direction(direction: str, limit: int = 6) -> list[dict]:
    return [item for item in LIBRARY_ITEMS if direction in item["directions"]][:limit]
