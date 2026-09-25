"""
Портфолио Дмитрия Степанова — Flask-приложение.

Запуск из корня проекта:
    python app.py
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import smtplib
import secrets
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from logging.handlers import RotatingFileHandler
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from sqlalchemy import or_
from flask import (
    Flask,
    abort,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy.exc import IntegrityError
from werkzeug.middleware.proxy_fix import ProxyFix

from assistant.answer import MAX_MESSAGE_LEN, answer_question
from assistant.rate_limit import SlidingWindowLimiter, limiter
from cases import FILTERS, get_all_cases, get_case
from clinical_guidelines import (
    GuidelineValidationError,
    OFFICIAL_SOURCES,
    fetch_minzdrav_page,
    public_guidelines_query,
    sync_guidelines_registry,
    sync_minzdrav,
    upsert_guideline,
)
from config import BASE_DIR, get_config
from docx_reader import read_docx_blocks
from editorial import (
    CONTENT_TYPE_LABELS,
    STATUS_LABELS,
    apply_article_form,
    ensure_editorial_seed,
    published_articles,
    recommended_for_case,
    related_articles,
    sources_as_text,
)
from editorial_workshop import EDITORIAL_SOURCES, EDITORIAL_STEPS
from extensions import csrf, db, login_manager
from forms import TOPIC_CHOICES, ArticleForm, InquiryForm, LoginForm
from lifeos_import import ImportValidationError, import_lifeos_package
from library_content import (
    LIBRARY_CATEGORIES,
    LIBRARY_ITEMS,
    featured_library_items,
    get_library_item,
    grouped_library_items,
    library_items_for_direction,
)
from models import (
    AdminUser,
    Article,
    ClinicalGuideline,
    ImportPackage,
    Inquiry,
    PortalVisit,
    Rubric,
    Tag,
)
from portal_content import PROJECT_FILTERS, PROJECTS, SECTIONS, get_section, get_topic

logger = logging.getLogger("st8dom")
login_limiter = SlidingWindowLimiter(max_hits=10, window_sec=900)
MOSCOW = ZoneInfo("Europe/Moscow")
BOT_MARKERS = ("bot", "crawler", "spider", "headless", "lighthouse", "preview", "monitor")


def visit_stats() -> dict[str, int]:
    """Визиты, начавшиеся сегодня и за 30 дней по московскому времени."""
    now = datetime.now(MOSCOW)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_utc = today.astimezone(timezone.utc).replace(tzinfo=None)
    month_utc = (today - timedelta(days=29)).astimezone(timezone.utc).replace(tzinfo=None)
    return {
        "today": PortalVisit.query.filter(PortalVisit.started_at >= today_utc).count(),
        "last_30_days": PortalVisit.query.filter(PortalVisit.started_at >= month_utc).count(),
        "total": PortalVisit.query.count(),
    }


def configure_logging(app: Flask) -> None:
    """Пишет основные действия в файл и в консоль."""
    log_path = Path(app.config["LOG_FILE"])
    log_path.parent.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    file_handler = RotatingFileHandler(
        log_path, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(app.config["LOG_LEVEL"])
    if not root.handlers:
        root.addHandler(file_handler)
        root.addHandler(stream_handler)


def hash_ip(ip: str | None) -> str | None:
    """Храним не сырой IP, а хэш — достаточно для антиспама без лишних ПДн."""
    if not ip:
        return None
    return hashlib.sha256(ip.encode("utf-8")).hexdigest()[:32]


def ensure_admin(app: Flask) -> None:
    """Создаёт администратора при пустой таблице пользователей."""
    if AdminUser.query.first():
        return
    username = app.config["ADMIN_USERNAME"]
    password = app.config["ADMIN_PASSWORD"]
    user = AdminUser(username=username)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    logger.info("Создан администратор по умолчанию: %s", username)



def notify_email(inquiry: Inquiry, app: Flask) -> bool:
    """Отправляет заявку владельцу сайта через SMTP; секреты берёт из окружения."""
    recipient = (app.config.get("INQUIRY_EMAIL") or "").strip()
    username = (app.config.get("SMTP_USERNAME") or "").strip()
    password = app.config.get("SMTP_PASSWORD") or ""
    sender = (app.config.get("SMTP_FROM") or username).strip()
    if not recipient or not username or not password or not sender:
        logger.warning(
            "Email-доставка не настроена — заявка #%s сохранена в БД", inquiry.id
        )
        return False

    message = EmailMessage()
    message["Subject"] = f"Новая заявка с st8dom.ru #{inquiry.id}"
    message["From"] = sender
    message["To"] = recipient
    message["Reply-To"] = inquiry.email
    message.set_content(
        "\n".join(
            [
                f"Заявка #{inquiry.id}",
                f"Имя: {inquiry.name}",
                f"Email: {inquiry.email}",
                f"Телефон: {inquiry.phone or '—'}",
                f"Компания: {inquiry.company or '—'}",
                f"Тема: {inquiry.topic}",
                "",
                inquiry.message,
            ]
        )
    )

    try:
        with smtplib.SMTP(
            app.config["SMTP_HOST"], app.config["SMTP_PORT"], timeout=10
        ) as smtp:
            smtp.ehlo()
            if app.config.get("SMTP_USE_TLS", True):
                smtp.starttls()
                smtp.ehlo()
            smtp.login(username, password)
            smtp.send_message(message)
        logger.info("Заявка #%s отправлена на email владельца", inquiry.id)
        return True
    except (OSError, smtplib.SMTPException):
        logger.exception(
            "Не удалось отправить заявку #%s на email; копия сохранена в БД",
            inquiry.id,
        )
        return False

def notify_telegram(inquiry: Inquiry, app: Flask) -> None:
    """Опциональная доставка заявки в личный чат. Без токена ничего не вызывает."""
    token = app.config.get("TELEGRAM_BOT_TOKEN") or ""
    chat_id = app.config.get("TELEGRAM_CHAT_ID") or ""
    if not token or not chat_id:
        logger.info("Telegram-адаптер не настроен — заявка #%s только в БД", inquiry.id)
        return
    text = (
        f"Новая заявка #{inquiry.id}\n"
        f"Имя: {inquiry.name}\n"
        f"Email: {inquiry.email}\n"
        f"Телефон: {inquiry.phone or '—'}\n"
        f"Компания: {inquiry.company or '—'}\n"
        f"Тема: {inquiry.topic}\n\n"
        f"{inquiry.message}"
    )
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=8,
        )
        response.raise_for_status()
        logger.info("Заявка #%s отправлена в Telegram", inquiry.id)
    except requests.RequestException:
        logger.exception("Не удалось отправить заявку #%s в Telegram", inquiry.id)


def create_app() -> Flask:
    app = Flask(
        __name__,
        instance_path=str(BASE_DIR / "instance"),
        instance_relative_config=True,
    )
    app.config.from_object(get_config())
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    # За reverse-proxy (Render, Fly) нужны X-Forwarded-* для HTTPS-cookie и IP.
    if os.environ.get("FLASK_ENV", "development") == "production":
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
        if app.config["SECRET_KEY"] == "dev-change-me-in-production":
            raise RuntimeError("Задайте SECRET_KEY в окружении перед продакшен-запуском.")
        if app.config["ADMIN_PASSWORD"] == "change-me-now":
            raise RuntimeError("Задайте ADMIN_PASSWORD в окружении перед продакшен-запуском.")

    configure_logging(app)
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    @app.before_request
    def protect_library_files():
        """Не отдаёт исходные DOCX, пока загрузки явно не разрешены."""
        if (
            request.path.startswith("/static/downloads/")
            and not app.config.get("LIBRARY_DOWNLOADS_ENABLED", False)
        ):
            abort(404)

    @app.before_request
    def count_public_visit():
        """Один визит на 30 минут, независимо от числа просмотренных страниц."""
        endpoint = request.endpoint or ""
        if (
            request.method != "GET"
            or not endpoint
            or endpoint.startswith(("admin_", "static", "api_"))
            or endpoint in {"robots", "sitemap"}
            or current_user.is_authenticated
            or any(marker in request.user_agent.string.lower() for marker in BOT_MARKERS)
        ):
            return
        now = datetime.now(timezone.utc)
        if session.get("visit_key") and session.get("visit_until", 0) > now.timestamp():
            return
        key = secrets.token_hex(24)
        session["visit_key"] = key
        session["visit_until"] = (now + timedelta(minutes=30)).timestamp()
        try:
            db.session.add(PortalVisit(visit_key=key, started_at=now.replace(tzinfo=None)))
            db.session.commit()
        except IntegrityError:
            db.session.rollback()

    @app.after_request
    def add_security_headers(response):
        """Добавляет базовые браузерные ограничения ко всем ответам сайта."""
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
        )
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.headers.setdefault(
            "Content-Security-Policy",
            "; ".join(
                [
                    "default-src 'self'",
                    "base-uri 'self'",
                    "object-src 'none'",
                    "frame-ancestors 'none'",
                    "form-action 'self'",
                    "script-src 'self' 'unsafe-inline'",
                    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
                    "font-src 'self' https://fonts.gstatic.com data:",
                    "img-src 'self' data:",
                    "media-src 'self'",
                    "connect-src 'self'",
                ]
            ),
        )
        if request.is_secure and not app.debug:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000"
            )
        if request.path.startswith("/admin/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @login_manager.user_loader
    def load_user(user_id: str):
        return db.session.get(AdminUser, int(user_id))

    def static_exists(relpath: str) -> bool:
        """Проверяет файл в static/ без обхода каталога. Плеер живёт и без MP4."""
        folder = Path(app.static_folder or "").resolve()
        path = (folder / relpath).resolve()
        try:
            path.relative_to(folder)
        except ValueError:
            return False
        return path.is_file()

    @app.context_processor
    def inject_globals():
        return {
            "site_url": app.config["SITE_URL"],
            "analytics_id": app.config.get("ANALYTICS_ID") or "",
            "telegram_url": url_for("telegram_placeholder"),
            "github_url": "https://github.com/dimitry8st-prog",
            "fl_url": "https://www.fl.ru/users/dimitry8st/",
            "kwork_url": "https://kwork.ru/user/stepanov_craft",
            "email_address": app.config["INQUIRY_EMAIL"],
            "static_exists": static_exists,
            "chat_enabled": bool(app.config.get("CHAT_ENABLED")),
            "library_downloads_enabled": bool(
                app.config.get("LIBRARY_DOWNLOADS_ENABLED", False)
            ),
            "visit_stats": visit_stats(),
        }

    @app.route("/")
    def index():
        form = InquiryForm()
        latest_materials = published_articles().order_by(
            Article.published_at.desc()
        ).limit(6).all()
        return render_template(
            "index.html",
            cases=get_all_cases(),
            latest_materials=latest_materials,
            library_preview=featured_library_items(),
            form=form,
            page_id="home",
        )

    @app.route("/cases/")
    def cases_list():
        return render_template(
            "cases.html",
            cases=get_all_cases(),
            filters=FILTERS,
            page_id="cases",
        )

    @app.route("/directions/<slug>/")
    def direction_detail(slug: str):
        section = get_section(slug)
        if not section:
            abort(404)
        related_projects = [
            project
            for project in PROJECTS
            if slug in project["areas"]
            or (slug == "life-os" and project["name"] == "Life-OS")
        ][:6]
        return render_template(
            "direction.html",
            section=section,
            slug=slug,
            related_projects=related_projects,
            latest_materials=published_articles()
            .filter_by(section=slug)
            .order_by(Article.published_at.desc())
            .limit(6)
            .all(),
            library_items=library_items_for_direction(slug),
            page_id=f"direction-{slug}",
        )

    @app.route("/directions/<section_slug>/<topic_slug>/")
    def topic_detail(section_slug: str, topic_slug: str):
        section = get_section(section_slug)
        topic = get_topic(section_slug, topic_slug)
        if not section or not topic:
            abort(404)
        rubric_slugs = [f"{topic_slug}-{slug}" for slug, _name in topic["rubrics"]]
        rubrics = Rubric.query.filter(Rubric.slug.in_(rubric_slugs)).all()
        rubric_by_slug = {rubric.slug: rubric for rubric in rubrics}
        rubric_cards = []
        for short_slug, name in topic["rubrics"]:
            full_slug = f"{topic_slug}-{short_slug}"
            rubric = rubric_by_slug.get(full_slug)
            count = published_articles().filter_by(rubric_id=rubric.id).count() if rubric else 0
            href = url_for("materials_catalog", section=section_slug, rubric=full_slug)
            if topic_slug == "clinical-guidelines" and short_slug in {
                "russian-guidelines",
                "international-guidelines",
            }:
                kind = "russian" if short_slug == "russian-guidelines" else "international"
                count = public_guidelines_query().filter_by(kind=kind).count()
                href = url_for("clinical_guidelines_catalog", kind=kind)
            rubric_cards.append(
                {"slug": full_slug, "name": name, "count": count, "href": href}
            )
        grouped_rubrics = []
        card_by_slug = {card["slug"]: card for card in rubric_cards}
        for group in topic.get("rubric_groups", []):
            cards = []
            for short_slug, label in group["rubrics"]:
                card = card_by_slug[f"{topic_slug}-{short_slug}"].copy()
                card["name"] = label
                cards.append(card)
            grouped_rubrics.append({**group, "cards": cards})
        articles = (
            published_articles()
            .join(Rubric)
            .filter(Rubric.slug.in_(rubric_slugs))
            .order_by(Article.published_at.desc())
            .all()
        )
        guidelines = []
        if topic_slug == "clinical-guidelines":
            guidelines = (
                public_guidelines_query()
                .order_by(ClinicalGuideline.published_on.desc(), ClinicalGuideline.id.desc())
                .limit(8)
                .all()
            )
        return render_template(
            "topic.html",
            section=section,
            section_slug=section_slug,
            topic=topic,
            rubrics=rubric_cards,
            grouped_rubrics=grouped_rubrics,
            materials=articles,
            guidelines=guidelines,
            page_id=f"direction-{section_slug}",
        )

    @app.route("/clinical-guidelines/")
    def clinical_guidelines_catalog():
        kind = request.args.get("kind", "").strip().lower()
        source_key = request.args.get("source", "").strip().lower()
        search = request.args.get("q", "").strip()
        query = public_guidelines_query()
        if kind in {"russian", "international"}:
            query = query.filter(ClinicalGuideline.kind == kind)
        else:
            kind = ""
        if source_key in OFFICIAL_SOURCES:
            query = query.filter(ClinicalGuideline.source_key == source_key)
        else:
            source_key = ""
        if search:
            pattern = f"%{search}%"
            query = query.filter(
                or_(
                    ClinicalGuideline.title.ilike(pattern),
                    ClinicalGuideline.organization.ilike(pattern),
                    ClinicalGuideline.codes.ilike(pattern),
                )
            )
        guidelines = query.order_by(
            ClinicalGuideline.published_on.desc(), ClinicalGuideline.id.desc()
        ).all()
        return render_template(
            "clinical_guidelines.html",
            guidelines=guidelines,
            official_sources=OFFICIAL_SOURCES,
            selected={"kind": kind, "source": source_key, "q": search},
            page_id="clinical-guidelines",
        )

    def require_guidelines_sync_token() -> None:
        configured = (app.config.get("GUIDELINES_SYNC_TOKEN") or "").strip()
        provided = request.headers.get("Authorization", "")
        if not configured:
            abort(503, description="Синхронизация рекомендаций не настроена.")
        expected = f"Bearer {configured}"
        if not hmac.compare_digest(provided, expected):
            abort(401)

    @app.post("/api/clinical-guidelines/sync/minzdrav/")
    @csrf.exempt
    def api_sync_minzdrav():
        require_guidelines_sync_token()
        try:
            page = max(1, int(request.args.get("page", "1")))
            page_size = min(100, max(5, int(request.args.get("page_size", "25"))))
            source_data = fetch_minzdrav_page(current_page=page, page_size=page_size)
            stats = sync_minzdrav(source_data["Data"])
            stats["page"] = page
            stats["page_size"] = page_size
            stats["total_records"] = int(source_data.get("TotalRecords") or 0)
            stats["total_pages"] = (
                (stats["total_records"] + page_size - 1) // page_size
                if stats["total_records"]
                else 0
            )
        except (requests.RequestException, RuntimeError, ValueError):
            logger.exception("Ошибка синхронизации рекомендаций Минздрава")
            return jsonify({"ok": False, "error": "official_source_unavailable"}), 502
        logger.info("Синхронизация рекомендаций Минздрава: %s", stats)
        return jsonify({"ok": True, **stats})

    @app.post("/api/clinical-guidelines/import/")
    @csrf.exempt
    def api_import_clinical_guideline():
        """Принимает одну карточку от адаптера n8n, но только с официального домена."""
        require_guidelines_sync_token()
        try:
            record, action = upsert_guideline(request.get_json(silent=True))
            db.session.commit()
        except GuidelineValidationError as exc:
            db.session.rollback()
            return jsonify({"ok": False, "error": str(exc)}), 400
        logger.info(
            "Импорт рекомендации %s:%s — %s",
            record.source_key,
            record.external_id,
            action,
        )
        return jsonify({"ok": True, "action": action, "id": record.id})

    @app.route("/telegram/")
    def telegram_placeholder():
        return render_template("telegram_placeholder.html", page_id="telegram")

    @app.route("/search/")
    def unified_search():
        search = request.args.get("q", "").strip()
        materials = []
        library_items = []
        projects = []
        if search:
            terms = [term.casefold() for term in search.split() if len(term) >= 2]
            for article in published_articles().all():
                tag_text = " ".join(tag.name for tag in article.tags)
                haystack = " ".join([article.title, article.summary, article.body, article.rubric.name, tag_text]).casefold()
                score = sum(3 if term in article.title.casefold() else 1 for term in terms if term in haystack)
                if score:
                    materials.append((score, article))
            materials = [item for _score, item in sorted(materials, key=lambda row: (row[0], row[1].published_at), reverse=True)]
            for item in LIBRARY_ITEMS:
                haystack = " ".join([item["title"], item["summary"], item["kind"]]).casefold()
                score = sum(3 if term in item["title"].casefold() else 1 for term in terms if term in haystack)
                if score:
                    library_items.append((score, item))
            library_items = [item for _score, item in sorted(library_items, key=lambda row: row[0], reverse=True)]
            for project in PROJECTS:
                haystack = " ".join([project["name"], project["summary"], *project["areas"]]).casefold()
                score = sum(3 if term in project["name"].casefold() else 1 for term in terms if term in haystack)
                if score:
                    projects.append((score, project))
            projects = [item for _score, item in sorted(projects, key=lambda row: row[0], reverse=True)]
        return render_template(
            "search.html",
            query=search,
            materials=materials,
            library_items=library_items,
            projects=projects,
            page_id="search",
        )

    @app.route("/materials/")
    def materials_catalog():
        query = published_articles()
        section = request.args.get("section", "").strip()
        rubric = request.args.get("rubric", "").strip()
        content_type = request.args.get("type", "").strip()
        tag = request.args.get("tag", "").strip()
        search = request.args.get("q", "").strip()

        if section in SECTIONS:
            query = query.filter(Article.section == section)
        if rubric:
            query = query.join(Rubric).filter(Rubric.slug == rubric)
        if content_type in CONTENT_TYPE_LABELS:
            query = query.filter(Article.content_type == content_type)
        if tag:
            query = query.join(Article.tags).filter(Tag.slug == tag)
        if search:
            pattern = f"%{search}%"
            query = query.filter(
                or_(
                    Article.title.ilike(pattern),
                    Article.summary.ilike(pattern),
                    Article.body.ilike(pattern),
                )
            )

        materials = query.order_by(Article.published_at.desc()).distinct().all()
        return render_template(
            "materials.html",
            materials=materials,
            rubrics=Rubric.query.order_by(Rubric.name).all(),
            tags=Tag.query.order_by(Tag.name).all(),
            sections=SECTIONS,
            content_type_labels=CONTENT_TYPE_LABELS,
            selected={
                "section": section,
                "rubric": rubric,
                "type": content_type,
                "tag": tag,
                "q": search,
            },
            page_id="materials",
        )

    @app.route("/library/")
    def library_catalog():
        category = request.args.get("category", "").strip()
        valid_categories = {item["slug"] for item in LIBRARY_CATEGORIES}
        if category not in valid_categories:
            category = ""
        return render_template(
            "library.html",
            groups=grouped_library_items(category),
            categories=LIBRARY_CATEGORIES,
            selected_category=category,
            total=len(LIBRARY_ITEMS),
            published=sum(1 for item in LIBRARY_ITEMS if item["file"]),
            page_id="library",
        )

    @app.route("/editorial-workshop/")
    def editorial_workshop():
        return render_template(
            "editorial_workshop.html",
            sources=EDITORIAL_SOURCES,
            steps=EDITORIAL_STEPS,
            page_id="library",
        )

    @app.route("/library/<slug>/")
    def library_detail(slug: str):
        item = get_library_item(slug)
        if item is None or not item["file"]:
            abort(404)
        docx_path = Path(app.static_folder or "") / "downloads" / item["file"]
        try:
            blocks = read_docx_blocks(str(docx_path.resolve()))
        except (FileNotFoundError, ValueError):
            logger.exception("Не удалось открыть онлайн-версию %s", slug)
            abort(404)
        return render_template(
            "library_detail.html",
            item=item,
            blocks=blocks,
            page_id="library",
        )

    @app.route("/materials/<slug>/")
    def material_detail(slug: str):
        article = published_articles().filter_by(slug=slug).first()
        if article is None:
            abort(404)
        return render_template(
            "material_detail.html",
            article=article,
            related=related_articles(article),
            content_type_labels=CONTENT_TYPE_LABELS,
            preview=False,
            page_id="material",
        )

    @app.route("/projects/")
    def projects_catalog():
        return render_template(
            "projects.html",
            projects=PROJECTS,
            filters=PROJECT_FILTERS,
            page_id="projects",
        )

    @app.route("/cases/<slug>/")
    def case_detail(slug: str):
        case = get_case(slug)
        if not case:
            abort(404)
        others = [item for item in get_all_cases() if item["slug"] != slug]
        return render_template(
            "case_detail.html",
            case=case,
            others=others,
            recommended_materials=recommended_for_case(case),
            page_id="case",
        )

    @app.route("/contact/", methods=["GET", "POST"])
    def contact():
        form = InquiryForm()
        if request.method == "GET":
            topic = request.args.get("topic", "")
            allowed = {value for value, _label in TOPIC_CHOICES}
            if topic in allowed:
                form.topic.data = topic
        if form.validate_on_submit():
            inquiry = Inquiry(
                name=form.name.data.strip(),
                email=form.email.data.strip().lower(),
                phone=(form.phone.data or "").strip() or None,
                company=(form.company.data or "").strip() or None,
                topic=form.topic.data,
                message=form.message.data.strip(),
                ip_hash=hash_ip(request.headers.get("X-Forwarded-For", request.remote_addr)),
            )
            db.session.add(inquiry)
            db.session.commit()
            logger.info("Новая заявка #%s сохранена", inquiry.id)
            email_sent = notify_email(inquiry, app)
            notify_telegram(inquiry, app)
            if email_sent:
                flash("Заявка отправлена. Отвечу в рабочее время на указанный email.", "success")
            else:
                flash(
                    "Заявка сохранена, но email-уведомление временно недоступно. "
                    "Я увижу её в панели сайта.",
                    "info",
                )
            return redirect(url_for("contact", sent=1))
        if request.method == "POST":
            logger.warning("Форма заявки не прошла валидацию: %s", form.errors)
        return render_template("contact.html", form=form, page_id="contact")

    @app.post("/chat/")
    def chat():
        if not app.config.get("CHAT_ENABLED"):
            return jsonify({"error": "chat_disabled"}), 503
        client_key = hash_ip(request.remote_addr) or "anon"
        if not limiter.allow(f"chat:{client_key}"):
            return jsonify(
                {
                    "answer": "Слишком много вопросов подряд. Подождите пару минут или оставьте заявку.",
                    "escalated": True,
                    "source": "limit",
                }
            ), 429
        payload = request.get_json(silent=True) or {}
        message = payload.get("message") if isinstance(payload, dict) else ""
        result = answer_question(message if isinstance(message, str) else "", app.config)
        logger.info("Чат: source=%s escalated=%s", result.get("source"), result.get("escalated"))
        return jsonify(result)

    @app.route("/privacy/")
    def privacy():
        return render_template("privacy.html", page_id="legal")

    @app.route("/consent/")
    def consent():
        return render_template("consent.html", page_id="legal")

    @app.route("/admin/login/", methods=["GET", "POST"])
    def admin_login():
        if current_user.is_authenticated:
            return redirect(url_for("admin_inquiries"))
        form = LoginForm()
        client_key = hash_ip(request.remote_addr) or "anon"
        if request.method == "POST" and not login_limiter.allow(
            f"admin-login:{client_key}"
        ):
            logger.warning("Лимит попыток входа превышен: %s", client_key)
            flash("Слишком много попыток входа. Повторите через 15 минут.", "error")
            return (
                render_template("admin/login.html", form=form, page_id="admin"),
                429,
                {"Retry-After": "900"},
            )
        if form.validate_on_submit():
            user = AdminUser.query.filter_by(username=form.username.data.strip()).first()
            if user and user.check_password(form.password.data):
                login_user(user)
                logger.info("Вход в админку: %s", user.username)
                return redirect(url_for("admin_inquiries"))
            logger.warning("Неудачный вход: %s", form.username.data)
            flash("Неверный логин или пароль.", "error")
        return render_template("admin/login.html", form=form, page_id="admin")

    @app.route("/admin/logout/")
    @login_required
    def admin_logout():
        logger.info("Выход из админки: %s", current_user.username)
        logout_user()
        flash("Вы вышли из панели.", "info")
        return redirect(url_for("admin_login"))

    @app.route("/admin/")
    @login_required
    def admin_inquiries():
        status = request.args.get("status", "all")
        query = Inquiry.query.order_by(Inquiry.created_at.desc())
        if status == "unread":
            query = query.filter_by(is_read=False)
        elif status == "read":
            query = query.filter_by(is_read=True)
        inquiries = query.all()
        unread_count = Inquiry.query.filter_by(is_read=False).count()
        return render_template(
            "admin/inquiries.html",
            inquiries=inquiries,
            status=status,
            unread_count=unread_count,
            page_id="admin",
        )

    def prepare_article_form(article: Article | None = None) -> ArticleForm:
        form = ArticleForm(obj=article)
        form.rubric_id.choices = [
            (rubric.id, f"{SECTIONS.get(rubric.section, {}).get('title', rubric.section)} · {rubric.name}")
            for rubric in Rubric.query.order_by(Rubric.section, Rubric.name).all()
        ]
        if article is not None and request.method == "GET":
            form.tags.data = ", ".join(article.tag_names)
            form.sources.data = sources_as_text(article)
            form.reviewed_confirmed.data = article.reviewed_at is not None
        if article is not None and article.is_public:
            form.status.choices = [
                *form.status.choices,
                ("published", "Опубликовано"),
            ]
        return form

    @app.route("/admin/articles/")
    @login_required
    def admin_articles():
        articles = Article.query.order_by(Article.updated_at.desc()).all()
        return render_template(
            "admin/articles.html",
            articles=articles,
            status_labels=STATUS_LABELS,
            page_id="admin",
        )

    @app.route("/admin/imports/life-os/", methods=["GET", "POST"])
    @login_required
    def admin_lifeos_import():
        raw = ""
        if request.method == "POST":
            raw = request.form.get("package", "")
            try:
                record, created = import_lifeos_package(raw)
                if created:
                    logger.info("Life-OS: импортирован пакет %s в черновик #%s", record.package_id, record.article_id)
                    flash("Пакет принят. Создан только черновик; публикация требует проверки.", "success")
                else:
                    flash("Этот пакет уже импортирован — дубликат не создан.", "info")
                return redirect(url_for("admin_article_edit", article_id=record.article_id))
            except ImportValidationError as exc:
                db.session.rollback()
                logger.warning("Life-OS: пакет отклонён: %s", exc)
                flash(str(exc), "error")
        imports = ImportPackage.query.order_by(ImportPackage.created_at.desc()).limit(50).all()
        return render_template("admin/lifeos_import.html", package=raw, imports=imports, page_id="admin")

    @app.route("/admin/articles/new/", methods=["GET", "POST"])
    @login_required
    def admin_article_create():
        article = Article()
        form = prepare_article_form()
        if form.validate_on_submit():
            if Article.query.filter_by(slug=form.slug.data.strip().lower()).first():
                form.slug.errors.append("Такой постоянный адрес уже используется.")
            else:
                errors = apply_article_form(article, form)
                if not errors:
                    db.session.add(article)
                    db.session.commit()
                    logger.info("Создан черновик статьи #%s", article.id)
                    flash("Материал сохранён. Проверьте предпросмотр перед публикацией.", "success")
                    return redirect(url_for("admin_article_edit", article_id=article.id))
                for error in errors:
                    flash(error, "error")
        return render_template(
            "admin/article_form.html",
            form=form,
            article=None,
            page_id="admin",
        )

    @app.route("/admin/articles/<int:article_id>/edit/", methods=["GET", "POST"])
    @login_required
    def admin_article_edit(article_id: int):
        article = db.session.get(Article, article_id)
        if article is None:
            abort(404)
        form = prepare_article_form(article)
        if form.validate_on_submit():
            duplicate = Article.query.filter(
                Article.slug == form.slug.data.strip().lower(),
                Article.id != article.id,
            ).first()
            if duplicate:
                form.slug.errors.append("Такой постоянный адрес уже используется.")
            else:
                errors = apply_article_form(article, form)
                if not errors:
                    db.session.commit()
                    logger.info("Статья #%s обновлена", article.id)
                    flash("Изменения сохранены.", "success")
                    return redirect(url_for("admin_article_edit", article_id=article.id))
                for error in errors:
                    flash(error, "error")
        return render_template(
            "admin/article_form.html",
            form=form,
            article=article,
            page_id="admin",
        )

    @app.route("/admin/articles/<int:article_id>/preview/")
    @login_required
    def admin_article_preview(article_id: int):
        article = db.session.get(Article, article_id)
        if article is None:
            abort(404)
        return render_template(
            "material_detail.html",
            article=article,
            related=[],
            content_type_labels=CONTENT_TYPE_LABELS,
            preview=True,
            page_id="admin",
        )

    @app.post("/admin/articles/<int:article_id>/publish/")
    @login_required
    def admin_article_publish(article_id: int):
        article = db.session.get(Article, article_id)
        if article is None:
            abort(404)
        errors = article.publish()
        if errors:
            flash("Публикация заблокирована: " + ", ".join(errors) + ".", "error")
            return redirect(url_for("admin_article_edit", article_id=article.id))
        db.session.commit()
        logger.info("Статья #%s опубликована", article.id)
        flash("Материал опубликован и добавлен в публичный каталог.", "success")
        return redirect(url_for("admin_article_edit", article_id=article.id))

    @app.post("/admin/articles/<int:article_id>/unpublish/")
    @login_required
    def admin_article_unpublish(article_id: int):
        article = db.session.get(Article, article_id)
        if article is None:
            abort(404)
        article.unpublish()
        db.session.commit()
        logger.info("Статья #%s снята с публикации", article.id)
        flash("Материал снят с публикации, публичный URL закрыт.", "info")
        return redirect(url_for("admin_article_edit", article_id=article.id))

    @app.post("/admin/inquiries/<int:inquiry_id>/read/")
    @login_required
    def admin_mark_read(inquiry_id: int):
        inquiry = db.session.get(Inquiry, inquiry_id)
        if not inquiry:
            abort(404)
        inquiry.mark_read()
        db.session.commit()
        logger.info("Заявка #%s отмечена прочитанной", inquiry_id)
        flash("Заявка отмечена как прочитанная.", "success")
        return redirect(url_for("admin_inquiries", status=request.args.get("status", "all")))

    @app.post("/admin/inquiries/<int:inquiry_id>/delete/")
    @login_required
    def admin_delete(inquiry_id: int):
        inquiry = db.session.get(Inquiry, inquiry_id)
        if not inquiry:
            abort(404)
        db.session.delete(inquiry)
        db.session.commit()
        logger.info("Заявка #%s удалена", inquiry_id)
        flash("Заявка удалена.", "info")
        return redirect(url_for("admin_inquiries", status=request.args.get("status", "all")))

    @app.route("/robots.txt")
    def robots():
        body = (
            "User-agent: *\n"
            "Allow: /\n"
            "Disallow: /admin/\n"
            f"Sitemap: {app.config['SITE_URL']}/sitemap.xml\n"
        )
        return body, 200, {"Content-Type": "text/plain; charset=utf-8"}

    @app.route("/sitemap.xml")
    def sitemap():
        origin = app.config["SITE_URL"]
        pages = [
            origin + "/",
            origin + url_for("cases_list"),
            origin + url_for("projects_catalog"),
            origin + url_for("library_catalog"),
            origin + url_for("editorial_workshop"),
            origin + url_for("contact"),
            origin + url_for("privacy"),
            origin + url_for("consent"),
            origin + url_for("clinical_guidelines_catalog"),
        ]
        pages.extend(
            origin + url_for("direction_detail", slug=slug) for slug in SECTIONS
        )
        pages.extend(
            origin + url_for("topic_detail", section_slug=section_slug, topic_slug=topic["slug"])
            for section_slug, section in SECTIONS.items()
            for topic in section["topics"]
        )
        pages.extend(origin + url_for("case_detail", slug=case["slug"]) for case in get_all_cases())
        pages.append(origin + url_for("materials_catalog"))
        pages.extend(
            origin + url_for("material_detail", slug=article.slug)
            for article in published_articles().all()
        )
        pages.extend(
            origin + url_for("library_detail", slug=item["slug"])
            for item in LIBRARY_ITEMS
            if item["file"]
        )
        xml_urls = "".join(f"<url><loc>{page}</loc></url>" for page in pages)
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            f"{xml_urls}</urlset>"
        )
        return xml, 200, {"Content-Type": "application/xml; charset=utf-8"}

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("errors/404.html", page_id="error"), 404

    @app.errorhandler(500)
    def server_error(_error):
        logger.exception("Внутренняя ошибка сервера")
        return render_template("errors/500.html", page_id="error"), 500

    with app.app_context():
        db.create_all()
        ensure_admin(app)
        ensure_editorial_seed()
        try:
            stats = sync_guidelines_registry(BASE_DIR / "data" / "clinical_guidelines.json")
            logger.info("Карточки рекомендаций загружены из GitHub-реестра: %s", stats)
        except (OSError, ValueError, GuidelineValidationError):
            db.session.rollback()
            logger.exception("Не удалось загрузить реестр клинических рекомендаций")

    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    # PaaS передаёт PORT — слушаем все интерфейсы. Локально остаёмся на localhost.
    host = "0.0.0.0" if os.environ.get("PORT") else "127.0.0.1"
    debug = os.environ.get("FLASK_ENV", "development") != "production"
    logger.info("Запуск сервера на %s:%s", host, port)
    app.run(host=host, port=port, debug=debug)
