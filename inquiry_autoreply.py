"""Ограниченный автоответ на вопросы о цене из формы портала."""

import hashlib
import hmac
import logging
import re
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

from sqlalchemy.exc import IntegrityError

from extensions import db
from models import InquiryAutoReply

logger = logging.getLogger("st8dom")

PRICE_WORDS = re.compile(
    r"(?:\bцен[ауеыой]\b|стоимост|прайс|сколько.{0,24}сто|"
    r"\b(?:price|pricing|cost|quote|rates?)\b|\bkain[aoą]\b)",
    re.IGNORECASE,
)
PROMOTION = re.compile(
    r"https?://|www\.|\b[\w-]+\.(?:com|net|ru|site|org)\b|"
    r"\b(?:backlinks?|seo|search index|ranking)\b",
    re.IGNORECASE,
)


def is_price_question(message: str) -> bool:
    """Не отвечаем на ссылки и SEO-рекламу даже при упоминании цены."""
    return bool(PRICE_WORDS.search(message)) and not bool(PROMOTION.search(message))


def send_price_auto_reply(inquiry, app, *, requested: bool) -> bool:
    """Одно безопасное письмо на адрес за календарную неделю, до 20 за сутки."""
    if not requested or not app.config.get("INQUIRY_AUTO_REPLY_ENABLED"):
        return False
    if not is_price_question(inquiry.message):
        return False

    username = (app.config.get("SMTP_USERNAME") or "").strip()
    password = app.config.get("SMTP_PASSWORD") or ""
    sender = (app.config.get("SMTP_FROM") or username).strip()
    email = inquiry.email.strip().lower()
    if not username or not password or not sender or not email or "\n" in email or "\r" in email:
        logger.info("Автоответ пропущен: SMTP не настроен, заявка #%s", inquiry.id)
        return False
    if email == (app.config.get("INQUIRY_EMAIL") or "").strip().lower():
        return False

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if InquiryAutoReply.query.filter(
        InquiryAutoReply.attempted_at >= now - timedelta(days=1)
    ).count() >= 20:
        logger.warning("Дневной предел автоответов достигнут, заявка #%s", inquiry.id)
        return False

    week_start = (now - timedelta(days=now.weekday())).date().isoformat()
    key = hmac.new(
        app.config["SECRET_KEY"].encode("utf-8"),
        f"{email}|{week_start}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    record = InquiryAutoReply(
        recipient_key=key, inquiry_id=inquiry.id, attempted_at=now
    )
    try:
        db.session.add(record)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        logger.info("Повторный автоответ пропущен, заявка #%s", inquiry.id)
        return False

    mail = EmailMessage()
    mail["Subject"] = "Уточнение по заявке на st8dom.ru"
    mail["From"] = sender
    mail["To"] = email
    mail["Reply-To"] = sender
    mail.set_content(
        "Здравствуйте!\n\n"
        "Спасибо за обращение. Стоимость зависит от задачи. "
        "Уточните, пожалуйста, какая услуга вас интересует, какой результат нужен "
        "и в какие сроки. После этого я подготовлю предложение и назову стоимость.\n\n"
        "Это автоматический ответ на вашу заявку. Вы можете ответить на это письмо.\n\n"
        "С уважением,\nДмитрий Степанов\nhttps://st8dom.ru\n"
    )
    try:
        with smtplib.SMTP(app.config["SMTP_HOST"], app.config["SMTP_PORT"], timeout=10) as smtp:
            smtp.ehlo()
            if app.config.get("SMTP_USE_TLS", True):
                smtp.starttls()
                smtp.ehlo()
            smtp.login(username, password)
            smtp.send_message(mail)
    except (OSError, smtplib.SMTPException, ValueError):
        logger.exception("Автоответ по заявке #%s не отправлен", inquiry.id)
        return False

    record.sent = True
    db.session.commit()
    logger.info("Автоответ по заявке #%s отправлен", inquiry.id)
    return True
