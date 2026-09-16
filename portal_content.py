"""Структура тематических разделов и витрина отобранных проектов портала ДИС."""

SECTIONS = {
    "medicine": {
        "title": "Медицина",
        "eyebrow": "Клинический опыт и проверенные источники",
        "summary": "Неврология, нейрохирургия и реабилитация — понятным языком для специалистов, пациентов и их близких.",
        "description": "Медицинские материалы портала ДИС: неврология, нейрохирургия, реабилитация, клинические рекомендации и памятки для пациентов.",
        "topics": [
            {"slug": "neurology-neurosurgery", "title": "Неврология и нейрохирургия", "description": "Разбор заболеваний, диагностики и маршрута пациента.", "rubrics": [("diseases", "Заболевания"), ("diagnostics", "Диагностика"), ("treatment-route", "Маршрут лечения"), ("surgery", "Нейрохирургия")]},
            {"slug": "rehabilitation", "title": "Реабилитация", "description": "Восстановление после инсульта и других поражений нервной системы.", "rubrics": [("after-stroke", "После инсульта"), ("movement", "Движение и координация"), ("speech-memory", "Речь и память"), ("home-care", "Восстановление дома")]},
            {"slug": "clinical-guidelines", "title": "Клинические рекомендации", "description": "Практические выводы с датой проверки и ссылками на источники.", "rubrics": [("russian-guidelines", "Российские рекомендации"), ("international-guidelines", "Международные рекомендации"), ("evidence-review", "Разбор доказательств"), ("updates", "Обновления документов")]},
            {"slug": "for-patients", "title": "Материалы для пациентов", "description": "Объяснения без лишней терминологии и обещаний лечения.", "rubrics": [("symptoms", "Симптомы и тревожные признаки"), ("doctor-visit", "Подготовка к врачу"), ("examinations", "Обследования понятным языком"), ("family-care", "Памятки для близких")]},
        ],
        "principles": ["источники и дата проверки", "отделение данных от личного опыта", "редакционная проверка автором"],
        "notice": "Материалы носят информационный характер и не заменяют очную консультацию врача.",
    },
    "ai": {
        "title": "AI на практике",
        "eyebrow": "От задачи до работающей системы",
        "summary": "Промпт-инжиниринг, RAG, AI-ассистенты и автоматизация с понятной архитектурой и проверяемым результатом.",
        "description": "Практические материалы портала ДИС об искусственном интеллекте, промптах, RAG, AI-ассистентах и автоматизации.",
        "topics": [
            {"slug": "learning", "title": "Обучающие статьи", "description": "Простые объяснения моделей, агентов и инструментов.", "rubrics": [("models", "Модели"), ("agents", "AI-агенты"), ("tools", "Инструменты"), ("safety", "Безопасность")]},
            {"slug": "prompts", "title": "Практические промпты", "description": "Шаблоны с назначением, ограничениями и примерами проверки.", "rubrics": [("work", "Для работы"), ("analysis", "Для анализа"), ("content", "Для контента"), ("verification", "Проверка результата")]},
            {"slug": "rag-assistants", "title": "RAG и AI-ассистенты", "description": "Поиск по документам, источники, эскалация человеку.", "rubrics": [("knowledge-bases", "Базы знаний"), ("search", "Поиск и источники"), ("integrations", "Интеграции"), ("evaluation", "Оценка качества")]},
            {"slug": "cases-projects", "title": "Кейсы и проекты", "description": "Репозитории, демонстрации, статус и честные ограничения.", "rubrics": [("business", "Для бизнеса"), ("medicine-ai", "Медицинский AI"), ("automation", "Автоматизация"), ("lessons", "Уроки разработки")]},
        ],
        "principles": ["сначала задача, затем технология", "контроль человека", "тесты и измеримые критерии"],
        "notice": "AI может ошибаться. Критичные решения должны подтверждаться специалистом.",
    },
    "longevity": {
        "title": "Долголетие и будущее человека",
        "eyebrow": "Наука, гипотезы и границы доказательности",
        "summary": "Исследования старения, здоровое долголетие, цифровое наследие, этика и сценарии будущего.",
        "description": "Материалы портала ДИС о науке старения, здоровом долголетии, будущем человека, цифровом наследии и этике.",
        "topics": [
            {"slug": "aging-science", "title": "Наука о старении", "description": "Механизмы, исследования и качество доказательств.", "rubrics": [("mechanisms", "Механизмы старения"), ("biomarkers", "Биомаркеры"), ("research", "Исследования"), ("evidence", "Качество доказательств")]},
            {"slug": "healthy-longevity", "title": "Здоровое долголетие", "description": "Подходы к сохранению функций и качества жизни.", "rubrics": [("activity", "Движение"), ("nutrition", "Питание"), ("sleep", "Сон"), ("prevention", "Профилактика")]},
            {"slug": "immortality", "title": "Бессмертие: наука и гипотезы", "description": "Смелые идеи с явным отделением фактов от предположений.", "rubrics": [("geroprotection", "Геропротекция"), ("regeneration", "Регенерация"), ("cryonics", "Крионика"), ("hypotheses", "Гипотезы будущего")]},
            {"slug": "digital-legacy", "title": "Цифровое наследие и этика", "description": "Сохранение знаний, личности и ответственность технологий.", "rubrics": [("knowledge", "Сохранение знаний"), ("digital-twin", "Цифровой двойник"), ("ethics", "Этика"), ("law", "Право и ответственность")]},
        ],
        "principles": ["без псевдонаучных обещаний", "уровень доказательности", "этический контекст"],
        "notice": "Гипотезы о продлении жизни не являются медицинскими рекомендациями.",
    },
    "life-os": {
        "title": "Life-OS",
        "eyebrow": "Личная система знаний за порталом",
        "summary": "Life-OS собирает материалы из URL, PDF, текста и YouTube, помогает их классифицировать и находить связи.",
        "description": "Life-OS — авторская система сбора, классификации и поиска знаний для подготовки материалов портала ДИС.",
        "topics": [
            {"slug": "capture", "title": "Сбор материалов", "description": "URL, PDF, текст и YouTube попадают в единый входящий поток.", "rubrics": [("urls", "Ссылки и статьи"), ("pdf", "PDF и документы"), ("video", "Видео"), ("notes", "Личные заметки")]},
            {"slug": "processing", "title": "Обработка", "description": "Классификация, краткое содержание, теги и научный контекст.", "rubrics": [("classification", "Классификация"), ("summaries", "Краткие выводы"), ("tags", "Теги и связи"), ("source-check", "Проверка источника")]},
            {"slug": "knowledge-library", "title": "Библиотека знаний", "description": "Заметки сохраняются в Obsidian и связываются по темам.", "rubrics": [("obsidian", "Obsidian"), ("structure", "Структура базы"), ("links", "Связи заметок"), ("archive", "Архив")]},
            {"slug": "search-collections", "title": "Поиск и подборки", "description": "Локальный поиск помогает возвращаться к источникам и готовить черновики.", "rubrics": [("local-search", "Локальный поиск"), ("collections", "Подборки"), ("drafts", "Черновики"), ("portal-export", "Передача в портал")]},
        ],
        "principles": ["источник сохраняется", "черновик не равен публикации", "медицинский контент проверяет автор"],
        "notice": "На сайт попадают только материалы, которые прошли авторскую проверку.",
        "repo_url": "https://github.com/dimitry8st-prog/Life-Os",
    },
}


PROJECTS = [
    {"name": "AutoSfera-AI", "summary": "AI-контур для продаж, сервиса и внутренних коммуникаций автодилера.", "group": "flagship", "areas": ["ai", "automation"], "repo": "AutoSfera-AI-", "case_slug": "autosfera-ai", "video": "autosfera-ai-defense.mp4", "poster": "autosfera-ai-defense-poster.png"},
    {"name": "Vitalis Medical AI", "summary": "Медицинский AI-ассистент для поиска и сравнения клинической информации с российским и международным контурами.", "group": "flagship", "areas": ["medicine", "ai", "rag"], "repo": "Vitalis-Medical-AI", "case_slug": "vitalis-medical-ai", "video": "vitalis-medical-ai.mp4", "poster": "Vitalis-Medical-AI-FL.png"},
    {"name": "KPI-Pulse", "summary": "Сбор показателей и подготовка понятных управленческих отчётов.", "group": "flagship", "areas": ["analytics", "automation"], "repo": "KPI-Pulse"},
    {"name": "Life-OS", "summary": "Сбор, классификация и поиск связанных знаний в Obsidian.", "group": "flagship", "areas": ["knowledge", "rag"], "repo": "Life-Os"},
    {"name": "DIS-Meeting-360", "summary": "Транскрибация встреч, выделение решений, рисков и следующих действий.", "group": "flagship", "areas": ["ai", "automation"], "repo": "meeting-360"},
    {"name": "DIS-Reputation-360", "summary": "Анализ отзывов и подготовка ответа с контролем оператора.", "group": "flagship", "areas": ["ai", "automation"], "repo": "-_-360", "case_slug": "dis-reputatsiya-360", "video": "dis-reputatsiya-360-16x9.mp4", "poster": "dis-reputatsiya-360-poster.jpg"},
    {"name": "DIS-AI-Mentor-360", "summary": "Персональное обучение, практика и проверка знаний.", "group": "quality", "areas": ["ai", "education"], "repo": "-AI--360", "case_slug": "ai-nastavnik-360", "video": "ai-nastavnik-360-16x9.mp4", "poster": "ai-nastavnik-360-poster.png"},
    {"name": "DIS-Analytics-360", "summary": "Разбор таблиц и документов с локальной визуализацией.", "group": "quality", "areas": ["analytics", "ai"], "repo": "-360", "case_slug": "dis-analyst-360", "video": "dis-analyst-360-16x9.mp4", "poster": "dis-analyst-360-poster.png"},
    {"name": "DocPulse-AI", "summary": "Структурированный разбор документов и медицинских PDF в Telegram.", "group": "quality", "areas": ["medicine", "rag"], "repo": "DocPulse---", "case_slug": "docpulse", "video": "docpulse-demo.mp4", "poster": "docpulse-demo-poster.png"},
    {"name": "LegalBot-AI", "summary": "Извлечение фактов из судебных документов и подготовка проекта апелляции.", "group": "quality", "areas": ["rag", "ai"], "repo": "JustBot", "case_slug": "legalbot", "video": "legalbot-demo.mp4", "poster": "legalbot-demo-poster.png"},
    {"name": "MedBot-AI", "summary": "Медицинский AI-ассистент с источниками и контролем клинических выводов.", "group": "quality", "areas": ["medicine", "rag"], "repo": "MedBot-AI"},
    {"name": "DIS-Lingua-360", "summary": "AI-репетитор английского и испанского с личной базой знаний.", "group": "quality", "areas": ["education", "rag"], "repo": "-Lingua-360"},
    {"name": "SAR-GPT-Analyzer", "summary": "Помощник для анализа радарных данных и работы в QGIS.", "group": "quality", "areas": ["analytics", "ai"], "repo": "QGIS-"},
    {"name": "HealthyStore", "summary": "Концепция интернет-магазина полезных и безглютеновых продуктов.", "group": "quality", "areas": ["web"], "repo": "Zdorowii_magazin", "case_slug": "healthy-store", "video": "biobalance-promo-16x9.mp4", "poster": "biobalance-promo-poster.webp"},
    {"name": "OnboardFlow-AI", "summary": "Онбординг сотрудников по проверенной корпоративной базе знаний.", "group": "quality", "areas": ["education", "rag"], "repo": "OnboardFlow_AI"},
]

PROJECT_FILTERS = [
    ("all", "Все 15"),
    ("flagship", "6 флагманов"),
    ("medicine", "Медицина"),
    ("ai", "AI"),
    ("rag", "RAG"),
    ("automation", "Автоматизация"),
]


def get_section(slug: str):
    return SECTIONS.get(slug)


def get_topic(section_slug: str, topic_slug: str):
    section = get_section(section_slug)
    if not section:
        return None
    return next((topic for topic in section["topics"] if topic["slug"] == topic_slug), None)


def rubric_catalog():
    """Рубрики навигации, доступные редакционной системе и импорту Life-OS."""
    for section_slug, section in SECTIONS.items():
        for topic in section["topics"]:
            for rubric_slug, rubric_name in topic["rubrics"]:
                yield {
                    "section": section_slug,
                    "topic_slug": topic["slug"],
                    "slug": f"{topic['slug']}-{rubric_slug}",
                    "name": rubric_name,
                    "description": topic["description"],
                }
