"""Редакционная логика портала: безопасные публикации и связи материалов."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from extensions import db
from models import Article, ArticleSource, ImportPackage, Rubric, Tag
from portal_content import rubric_catalog


STATUS_LABELS = {
    "draft": "Черновик",
    "review": "На проверке",
    "ready": "Готово",
    "published": "Опубликовано",
    "archive": "Архив",
}

CONTENT_TYPE_LABELS = {
    "article": "Статья",
    "review": "Обзор",
    "recommendation": "Рекомендация",
    "analysis": "Разбор",
    "patient": "Материал пациенту",
}

CONTENT_PACKAGES_DIR = Path(__file__).resolve().parent / "data" / "content-packages"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def tag_slug(value: str) -> str:
    """Стабильный URL-совместимый идентификатор для русских и латинских тегов."""
    return re.sub(r"[^\w]+", "-", value.casefold(), flags=re.UNICODE).strip("-")


def parse_tags(raw: str) -> list[str]:
    result = []
    seen = set()
    for part in raw.split(","):
        name = part.strip()
        key = name.casefold()
        if name and key not in seen:
            seen.add(key)
            result.append(name)
    return result


def parse_sources(raw: str) -> tuple[list[tuple[str, str]], list[str]]:
    """Читает строки `Название | URL` и отклоняет небезопасные адреса."""
    sources = []
    errors = []
    seen_urls = set()
    for number, line in enumerate(raw.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        if "|" not in line:
            errors.append(f"Источник {number}: добавьте разделитель | между названием и URL.")
            continue
        title, url = (part.strip() for part in line.split("|", 1))
        parsed = urlparse(url)
        if not title:
            errors.append(f"Источник {number}: отсутствует название.")
        elif parsed.scheme not in {"http", "https"} or not parsed.netloc:
            errors.append(f"Источник {number}: нужен полный адрес http(s).")
        elif url not in seen_urls:
            seen_urls.add(url)
            sources.append((title, url))
    return sources, errors


def sources_as_text(article: Article) -> str:
    return "\n".join(f"{source.title} | {source.url}" for source in article.sources)


def apply_article_form(article: Article, form) -> list[str]:
    """Применяет проверенную форму, не разрешая обойти кнопку публикации."""
    sources, source_errors = parse_sources(form.sources.data or "")
    if source_errors:
        return source_errors
    rubric = db.session.get(Rubric, form.rubric_id.data)
    if rubric is None or rubric.section != form.section.data:
        return ["Выбранная рубрика не относится к указанному разделу."]

    article.title = form.title.data.strip()
    article.slug = form.slug.data.strip().lower()
    article.summary = form.summary.data.strip()
    article.body = form.body.data.strip()
    article.section = form.section.data
    article.rubric_id = form.rubric_id.data
    article.content_type = form.content_type.data
    article.status = form.status.data
    article.author = form.author.data.strip()
    article.medical_reviewer = (form.medical_reviewer.data or "").strip() or None
    article.disclaimer = (form.disclaimer.data or "").strip() or None
    article.revision_note = (form.revision_note.data or "").strip() or None
    article.is_featured = bool(form.is_featured.data)
    article.reviewed_at = utcnow() if form.reviewed_confirmed.data else None

    tags = []
    for name in parse_tags(form.tags.data or ""):
        slug = tag_slug(name)
        tag = Tag.query.filter_by(slug=slug).first()
        if tag is None:
            tag = Tag(name=name, slug=slug)
        tags.append(tag)
    article.tags = tags

    article.sources.clear()
    article.sources.extend(
        ArticleSource(title=title, url=url) for title, url in sources
    )
    return []


def ensure_published_content_package(
    filename: str, published_at: datetime, *, update_published: bool = False
) -> None:
    """Публикует одобренный пакет и безопасно подхватывает прежний черновик."""
    package_path = CONTENT_PACKAGES_DIR / filename
    payload = json.loads(package_path.read_text(encoding="utf-8"))
    if payload.get("workflow_status") != "approved":
        raise ValueError(f"Пакет {filename} не получил редакционное одобрение.")

    article_data = payload["article"]
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    checksum = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    rubric = Rubric.query.filter_by(
        slug=article_data["rubric"], section=article_data["section"]
    ).one()
    article = Article.query.filter_by(slug=article_data["slug"]).first()
    record = ImportPackage.query.filter_by(package_id=payload["package_id"]).first()

    if article is not None and article.is_public:
        if record is None:
            record = ImportPackage(package_id=payload["package_id"], article=article)
            db.session.add(record)
        if not update_published or (record.checksum == checksum and article.body == article_data["body"]):
            record.checksum = checksum
            record.generator_version = payload["generator_version"]
            record.status = "published"
            return

    tags = []
    for name in article_data["tags"]:
        slug = tag_slug(name)
        tags.append(Tag.query.filter_by(slug=slug).first() or Tag(name=name, slug=slug))

    sources = [
        ArticleSource(title=source["title"], url=source["url"])
        for source in payload["sources"]
    ]
    if article is None:
        article = Article(slug=article_data["slug"])
        db.session.add(article)
    else:
        article.sources.clear()
        # Удаляем старые URL до вставки новых: на (article_id, url) есть UNIQUE.
        db.session.flush()

    article.title = article_data["title"]
    article.summary = article_data["summary"]
    article.body = article_data["body"]
    article.section = article_data["section"]
    article.rubric = rubric
    article.content_type = article_data["content_type"]
    article.status = "ready"
    article.author = article_data.get("author", "Степанов Д.А.")
    article.medical_reviewer = article_data.get("medical_reviewer")
    article.disclaimer = article_data.get("disclaimer")
    article.revision_note = article_data.get(
        "revision_note", "Материал и источники проверены 18 сентября 2026 года."
    )
    article.is_featured = True
    article.reviewed_at = published_at
    article.tags = tags
    article.sources = sources

    db.session.flush()
    errors = article.publish()
    if errors:
        raise ValueError(f"Пакет {filename} нельзя опубликовать: {', '.join(errors)}")
    article.published_at = published_at

    if record is None:
        record = ImportPackage(package_id=payload["package_id"], article=article)
        db.session.add(record)
    record.article = article
    record.checksum = checksum
    record.generator_version = payload["generator_version"]
    record.status = "published"


def ensure_editorial_seed() -> None:
    """Создаёт проверенные стартовые материалы и недостающие рубрики."""
    for item in rubric_catalog():
        if Rubric.query.filter_by(slug=item["slug"]).first() is None:
            db.session.add(Rubric(name=item["name"], slug=item["slug"], section=item["section"], description=item["description"]))

    db.session.flush()

    rubric = Rubric.query.filter_by(slug="medical-ai").first()
    if rubric is None:
        rubric = Rubric(
            name="Медицинский AI",
            slug="medical-ai",
            section="medicine",
            description="Безопасное применение AI для поиска и разбора медицинских источников.",
        )
        db.session.add(rubric)

    if not Article.query.filter_by(slug="kak-vitalis-proveryaet-istochniki").first():
        tags = []
        for name in ["Медицина", "AI", "RAG", "Источники"]:
            slug = tag_slug(name)
            tag = Tag.query.filter_by(slug=slug).first() or Tag(name=name, slug=slug)
            tags.append(tag)

        db.session.add(
            Article(
                title="Как Vitalis проверяет медицинские источники",
                slug="kak-vitalis-proveryaet-istochniki",
                summary=(
                    "Коротко о том, как российский и международный контуры Vitalis ищут "
                    "материалы, показывают источники и сохраняют решение за врачом."
                ),
                body=(
                    "Vitalis разделяет российский и международный поиск. Это помогает не "
                    "смешивать документы разных систем здравоохранения и сразу видеть, к "
                    "какому контуру относится найденный материал.\n\n"
                    "Сначала система проверяет локальную базу знаний, затем дополняет ответ "
                    "веб-поиском. Российская ветка отдаёт приоритет официальным клиническим "
                    "рекомендациям, профильным НМИЦ и профессиональным медицинским источникам.\n\n"
                    "Найденный материал не попадает в базу знаний автоматически. Он получает "
                    "статус кандидата и должен быть проверен человеком. Если веб-поиск "
                    "недоступен или подтверждений недостаточно, это ограничение показывается "
                    "в ответе.\n\n"
                    "Vitalis остаётся справочным инструментом. Окончательная оценка источника, "
                    "его применимости и клиническое решение принадлежат специалисту."
                ),
                section="medicine",
                rubric=rubric,
                content_type="analysis",
                status="published",
                author="Степанов Д.А.",
                medical_reviewer="Степанов Д.А.",
                disclaimer=(
                    "Материал носит информационный характер, не ставит диагноз и не заменяет "
                    "клиническое решение врача."
                ),
                is_featured=True,
                reviewed_at=utcnow(),
                published_at=utcnow(),
                tags=tags,
                sources=[
                    ArticleSource(
                        title="Vitalis Medical AI — открытый репозиторий проекта",
                        url="https://github.com/dimitry8st-prog/Vitalis-Medical-AI",
                    )
                ],
            )
        )

    ensure_published_content_package(
        "nighteagle-2026-09.json",
        datetime(2026, 9, 18, tzinfo=timezone.utc),
    )
    ensure_published_content_package(
        "botulinum-orofacial-pain-2026-09.json",
        datetime(2026, 9, 18, tzinfo=timezone.utc),
    )
    ensure_published_content_package(
        "openai-claude-hack-2026-09.json",
        datetime(2026, 9, 19, tzinfo=timezone.utc),
    )
    ensure_published_content_package(
        "tardigrades-2026-09.json",
        datetime(2026, 9, 21, tzinfo=timezone.utc),
    )
    ensure_published_content_package(
        "post-stroke-cognitive-tech-2026-09.json",
        datetime(2026, 9, 21, tzinfo=timezone.utc),
    )
    ensure_published_content_package(
        "ai-agent-sandbox-2026-09.json",
        datetime(2026, 9, 21, 18, 30, tzinfo=timezone.utc),
    )
    ensure_published_content_package(
        "gpt-6-claude-opus-5-5-2026-09.json",
        datetime(2026, 9, 23, 13, 0, tzinfo=timezone.utc),
    )
    ensure_published_content_package(
        "nemotron-3-diarization-2026-09.json",
        datetime(2026, 9, 25, 5, 45, tzinfo=timezone.utc),
    )
    ensure_published_content_package(
        "inflammaging-2026-09.json",
        datetime(2026, 9, 25, 9, 29, tzinfo=timezone.utc),
        update_published=True,
    )

    stroke_slug = "reabilitaciya-posle-ishemicheskogo-insulta"
    if not Article.query.filter_by(slug=stroke_slug).first():
        stroke_rubric = Rubric.query.filter_by(
            slug="neurology-neurosurgery-neurology-rehabilitation"
        ).one()
        stroke_tags = []
        for name in [
            "Ишемический инсульт",
            "Неврология",
            "Реабилитация",
            "Восстановление после инсульта",
        ]:
            slug = tag_slug(name)
            tag = Tag.query.filter_by(slug=slug).first() or Tag(name=name, slug=slug)
            stroke_tags.append(tag)

        body = """## Периоды ишемического инсульта

Реабилитация начинается не после выписки, а уже в сосудистом отделении. Её задачи — предупредить осложнения и помочь человеку восстановить движения, речь, память и бытовую самостоятельность.

Единой программы для всех нет. Объём и интенсивность занятий зависят от тяжести инсульта, локализации поражения, сопутствующих заболеваний, общего состояния и переносимости нагрузки.

Российские клинические рекомендации выделяют пять периодов ишемического инсульта:

| Период | Срок от начала инсульта |
| --- | --- |
| Острейший | Первые 3 суток |
| Острый | 4–28-е сутки |
| Ранний восстановительный | С 29-х суток до 6 месяцев |
| Поздний восстановительный | От 6 месяцев до 2 лет |
| Период остаточных явлений | После 2 лет |

Календарный срок помогает определить задачи лечения, но не является единственным критерием. Даже спустя несколько лет занятия могут приносить пользу, если у человека сохраняются конкретные проблемы и достижимые цели.

## Острейший период: первые 3 суток

В первые часы и дни главное — лечение самого инсульта. Пациенту проводят нейровизуализацию, оценивают показания к тромболитической терапии или внутрисосудистой тромбэкстракции, контролируют дыхание, артериальное давление, сердечный ритм, температуру и уровень глюкозы.

Одновременно начинается профилактика осложнений:

- оценка глотания и риска аспирации;
- правильное положение тела и конечностей;
- профилактика тромбозов, пролежней и контрактур;
- контроль питания и водного баланса;
- пассивные движения по индивидуальным показаниям;
- оценка готовности к дальнейшей активизации.

Чрезмерно ранняя и интенсивная мобилизация может быть небезопасной. Активную мобилизацию обычно не начинают раньше 24 часов от начала инсульта. При стабильном состоянии перевод в вертикальное положение возможен со вторых суток после оценки переносимости нагрузки.

## Острый период: 4–28-е сутки

После стабилизации состояния восстановление становится активнее. Если противопоказаний нет, реабилитационные мероприятия рекомендуется начинать не позднее 48 часов после поступления в стационар.

В этот период используют короткие, но регулярные занятия:

- повороты и перемещение в постели;
- переход в положение сидя;
- вставание и первые шаги;
- восстановление движений руки и ноги;
- обучение безопасному приёму пищи;
- занятия с логопедом при нарушениях речи — афазии и дизартрии;
- коррекция нарушений глотания;
- восстановление навыков одевания, гигиены и самообслуживания;
- оценка памяти, внимания и эмоционального состояния.

Работу проводит мультидисциплинарная команда. В неё могут входить невролог, врач физической и реабилитационной медицины, специалист по лечебной физкультуре, эрготерапевт, логопед, медицинский психолог и медицинские сёстры.

Родственников важно обучить безопасному уходу. Чрезмерное ограничение активности или попытки силой разрабатывать конечности могут причинить вред.

## Ранний восстановительный период: с 29-х суток до 6 месяцев

В первые месяцы восстановительные процессы обычно идут наиболее активно. Результат зависит не только от времени, но и от регулярности занятий.

Основные направления реабилитации:

- восстановление ходьбы и равновесия;
- улучшение функции руки и кисти;
- тренировка повседневных действий;
- восстановление речи;
- коррекция нарушений памяти и внимания;
- коррекция нарушения глотания — дисфагии;
- коррекция боли и спастичности;
- профилактика падений;
- психологическая поддержка;
- вторичная профилактика инсульта.

Основа двигательной реабилитации — многократное выполнение полезных действий. Человек не просто «разрабатывает руку», а учится брать предметы, пользоваться ложкой и застёгивать одежду. Не просто двигает ногой, а тренирует вставание, перенос веса и ходьбу.

Нагрузка должна быть достаточной, но переносимой. Для пациентов с двигательными целями, способных выдержать такую интенсивность, британские рекомендации 2023 года предусматривают не менее трёх часов многопрофильной терапии в день как минимум пять дней в неделю. Программа остаётся индивидуальной: учитываются сопутствующие заболевания, утомляемость, цели и переносимость нагрузки.

## Поздний восстановительный период: от 6 месяцев до 2 лет

После шести месяцев скорость восстановления нередко снижается, но улучшение всё ещё возможно. Программа становится более ориентированной на конкретные жизненные задачи:

- дальнейшее улучшение ходьбы и функции кисти;
- коррекция спастичности, контрактур и постинсультной боли;
- продолжение речевых и когнитивных занятий;
- повышение самостоятельности дома;
- возвращение к социальной активности и работе;
- адаптация жилища;
- подбор ортезов и технических средств реабилитации.

Цели нужно регулярно пересматривать. Если прежняя программа перестала давать результат, следует обсудить со специалистами изменение упражнений, нагрузки или направления работы.

## Период остаточных явлений: после 2 лет

Название периода не означает, что реабилитация больше не нужна. Давность инсульта сама по себе не позволяет сделать вывод, что реабилитационный потенциал исчерпан.

Даже спустя несколько лет могут быть актуальны:

- поддержание ходьбы и общей физической активности;
- профилактика падений;
- сохранение подвижности суставов;
- коррекция спастичности и боли;
- повышение бытовой самостоятельности;
- занятия при сохраняющихся речевых нарушениях;
- лечение тревоги и депрессии;
- социальная адаптация;
- профилактика повторного инсульта.

Желательна периодическая комплексная оценка. При появлении новых целей или ухудшении функций врач может повторно направить пациента на реабилитацию.

## Три этапа медицинской реабилитации

Периоды инсульта не следует путать с этапами организации помощи.

- Первый этап проходит в реанимации, сосудистом или неврологическом отделении одновременно с основным лечением.
- Второй этап проходит в специализированном стационарном отделении медицинской реабилитации.
- Третий этап проводится амбулаторно, в дневном стационаре, реабилитационном центре, санаторной организации или на дому.

Маршрут зависит от состояния пациента, необходимости круглосуточного наблюдения и оценки по шкале реабилитационной маршрутизации.

## Медикаментозная поддержка

Лекарственная терапия не заменяет двигательную, речевую, когнитивную и бытовую реабилитацию. Она может применяться как часть комплексного лечения с учётом вида инсульта, проведённой реперфузионной терапии, сопутствующих заболеваний и противопоказаний.

В российских клинических рекомендациях цитиколин указан как средство, которое может применяться для улучшения функционального исхода при ишемическом инсульте. Дополнительный эффект может быть менее выражен у пациентов после успешного восстановления кровотока с помощью тромболизиса или тромбэкстракции.

Полипептиды коры головного мозга скота рекомендуются пациентам с нетяжёлым ишемическим инсультом в системе сонных артерий при оценке менее 20 баллов по шкале тяжести инсульта NIHSS. В рекомендациях приведена схема: 20 мг внутримышечно в течение 10 дней, перерыв 10 дней и повторный десятидневный курс. Уровень доказательности этой рекомендации ниже, чем у рекомендации по цитиколину.

Любые препараты должен назначать врач. Нельзя переносить одну схему лечения на всех пациентов независимо от вида, тяжести и срока инсульта.

## Личный клинический опыт

В 2025–2026 годах я наблюдал около 100 пациентов преимущественно в раннем и позднем восстановительных периодах инсульта. В составе комплексного лечения применялась медикаментозная поддержка цитиколином и полипептидами коры головного мозга скота.

В моей практике полипептиды (кортексин) использовались в дозировке 10–20 мг в сутки курсом от 10 до 20 дней с возможным повторением через два месяца. Цитиколин применялся по 1000 мг внутримышечно в течение 10 дней с последующим переходом на приём 1000 мг внутрь продолжительностью до трёх месяцев.

По моим наблюдениям, такая поддержка вместе с полноценной реабилитацией сопровождалась улучшением результатов восстановления. Это личный клинический опыт: он не доказывает самостоятельную эффективность препаратов и не заменяет данные контролируемых исследований или индивидуальное назначение врача.

## Заключение

Восстановление после инсульта начинается в первые дни заболевания и может продолжаться годами. Его основные условия:

- раннее, но безопасное начало;
- индивидуальная программа;
- регулярные занятия;
- многократное выполнение полезных действий;
- участие специалистов разных направлений;
- обучение родственников;
- контроль осложнений;
- вторичная профилактика инсульта;
- периодическая оценка результатов.

Главная цель реабилитации — не выполнение набора процедур, а возвращение человеку максимально возможной самостоятельности, повышение качества жизни и улучшение социальной адаптации."""

        source_data = [
            ("Минздрав России. Ишемический инсульт и транзиторная ишемическая атака: клинические рекомендации, КР №814_1", "https://cr.minzdrav.gov.ru/preview-cr/814_1"),
            ("Приказ Минздрава России №788н: порядок организации медицинской реабилитации взрослых", "https://www.consultant.ru/document/cons_doc_LAW_363102/"),
            ("National Clinical Guideline for Stroke. Rehabilitation and recovery, 2023", "https://www.strokeguideline.org/chapter/rehabilitation-and-recovery-principles-of-rehabilitation/"),
            ("NICE NG236. Stroke rehabilitation in adults, 2023", "https://www.nice.org.uk/guidance/ng236"),
            ("VA/DoD Clinical Practice Guideline for Management of Stroke Rehabilitation, 2024", "https://www.healthquality.va.gov/guidelines/Rehab/stroke/VADoD-2024-Stroke-Rehab-CPG-Full-CPG_final_508.pdf"),
            ("Canadian Stroke Best Practice Recommendations: rehabilitation planning, 2025", "https://pubmed.ncbi.nlm.nih.gov/41257448/"),
            ("Canadian Stroke Best Practice Recommendations: delivery of rehabilitation, 2025", "https://pubmed.ncbi.nlm.nih.gov/41257457/"),
            ("Canadian Stroke Best Practice Recommendations: activity and community participation, 2025", "https://pubmed.ncbi.nlm.nih.gov/41258868/"),
            ("Всемирная организация здравоохранения. Реабилитация, 2024", "https://www.who.int/ru/news-room/fact-sheets/detail/rehabilitation"),
            ("Richards et al. AHA/ASA Guideline for Adult Stroke Rehabilitation and Recovery, 2026", "https://doi.org/10.1161/STR.0000000000000536"),
            ("AVERT Trial Collaboration. Very early mobilisation after stroke, 2015", "https://doi.org/10.1016/S0140-6736(15)60690-0"),
            ("Stroke Unit Trialists’ Collaboration. Organised inpatient stroke unit care, 2020", "https://doi.org/10.1002/14651858.CD000197.pub4"),
            ("Langhorne, Baylan. Early supported discharge services after stroke, 2017", "https://doi.org/10.1002/14651858.CD000443.pub4"),
            ("French et al. Repetitive task training for improving functional ability after stroke, 2016", "https://doi.org/10.1002/14651858.CD006073.pub3"),
            ("Legg et al. Occupational therapy for adults with problems in activities of daily living after stroke, 2017", "https://doi.org/10.1002/14651858.CD003585.pub3"),
        ]
        reviewed_at = datetime(2026, 9, 16, tzinfo=timezone.utc)
        db.session.add(
            Article(
                title="Реабилитация после ишемического инсульта: задачи на разных этапах восстановления",
                slug=stroke_slug,
                summary=(
                    "Что происходит в острейшем, остром и восстановительных периодах "
                    "ишемического инсульта: задачи команды, пациента и близких."
                ),
                body=body,
                section="medicine",
                rubric=stroke_rubric,
                content_type="article",
                status="published",
                author="Степанов Д.А.",
                medical_reviewer="Степанов Д.А.",
                disclaimer=(
                    "Материал носит информационный характер, не заменяет обследование "
                    "и индивидуальные назначения врача."
                ),
                revision_note="Материал и источники проверены 16 сентября 2026 года.",
                is_featured=True,
                reviewed_at=reviewed_at,
                published_at=reviewed_at,
                tags=stroke_tags,
                sources=[
                    ArticleSource(title=title, url=url) for title, url in source_data
                ],
            )
        )

    db.session.commit()


def published_articles():
    return Article.query.filter_by(status="published").filter(
        Article.published_at.is_not(None)
    )


def related_articles(article: Article, limit: int = 3) -> list[Article]:
    own_tags = {tag.slug for tag in article.tags}
    candidates = published_articles().filter(Article.id != article.id).all()
    ranked = sorted(
        candidates,
        key=lambda item: (
            len(own_tags & {tag.slug for tag in item.tags}),
            item.section == article.section,
            item.published_at,
        ),
        reverse=True,
    )
    return ranked[:limit]


def recommended_for_case(case: dict, limit: int = 3) -> list[Article]:
    keywords = {
        str(value).casefold()
        for value in [case.get("slug"), *case.get("filters", []), *case.get("tech", [])]
        if value
    }
    candidates = published_articles().all()

    def score(article: Article):
        article_keys = {tag.name.casefold() for tag in article.tags} | {
            tag.slug.casefold() for tag in article.tags
        }
        return (len(keywords & article_keys), article.is_featured, article.published_at)

    return sorted(candidates, key=score, reverse=True)[:limit]
