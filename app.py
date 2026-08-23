"""
Портфолио Дмитрия Степанова — Flask-приложение.

Запуск из корня проекта:
    python app.py
"""

from __future__ import annotations

import hashlib
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

import requests
from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.middleware.proxy_fix import ProxyFix

from assistant.answer import MAX_MESSAGE_LEN, answer_question
from assistant.rate_limit import limiter
from cases import FILTERS, get_all_cases, get_case
from config import BASE_DIR, get_config
from extensions import csrf, db, login_manager
from forms import TOPIC_CHOICES, InquiryForm, LoginForm
from models import AdminUser, Inquiry

logger = logging.getLogger("st8dom")


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

    configure_logging(app)
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

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
            "telegram_url": "https://t.me/+VNBg4iudNxw2Mzgy",
            "github_url": "https://github.com/dimitry8st-prog",
            "fl_url": "https://www.fl.ru/users/dimitry8st/",
            "kwork_url": "https://kwork.ru/user/stepanov_craft",
            "email_address": "dimitry.analytix@gmail.com",
            "static_exists": static_exists,
            "chat_enabled": bool(app.config.get("CHAT_ENABLED")),
        }

    @app.route("/")
    def index():
        form = InquiryForm()
        return render_template(
            "index.html",
            cases=get_all_cases(),
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
            logger.info("Новая заявка #%s от %s (%s)", inquiry.id, inquiry.name, inquiry.email)
            notify_telegram(inquiry, app)
            flash("Заявка отправлена. Отвечу в рабочее время на указанный email.", "success")
            return redirect(url_for("contact", sent=1))
        if request.method == "POST":
            logger.warning("Форма заявки не прошла валидацию: %s", form.errors)
        return render_template("contact.html", form=form, page_id="contact")

    @app.post("/chat/")
    def chat():
        if not app.config.get("CHAT_ENABLED"):
            return jsonify({"error": "chat_disabled"}), 503
        client_key = hash_ip(request.headers.get("X-Forwarded-For", request.remote_addr)) or "anon"
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
            origin + url_for("contact"),
            origin + url_for("privacy"),
            origin + url_for("consent"),
        ]
        pages.extend(origin + url_for("case_detail", slug=case["slug"]) for case in get_all_cases())
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

    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    # PaaS передаёт PORT — слушаем все интерфейсы. Локально остаёмся на localhost.
    host = "0.0.0.0" if os.environ.get("PORT") else "127.0.0.1"
    debug = os.environ.get("FLASK_ENV", "development") != "production"
    logger.info("Запуск сервера на %s:%s", host, port)
    app.run(host=host, port=port, debug=debug)
