"""Оформление заказа и устойчивые уведомления без модели и новых платежей.

HTTP-обработчики только фиксируют события. SMTP выполняет отдельная CLI-задача.
Номер заказа и цена берутся из БД; деньги переводит исключительно Robokassa.
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
import smtplib
import ssl
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from urllib.parse import urlsplit

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.exc import IntegrityError

from extensions import db
from models import Order, OrderCheckout, OrderNotification

logger = logging.getLogger("st8dom")
INITIAL_PAYMENT_STATES = {"new", "payment_pending", "payment_failed"}
NOTICE_LABELS = {
    "pending": "Ожидает отправки",
    "sending": "Отправляется",
    "sent": "Принято почтовым сервером",
    "failed": "Не отправлено",
    "unknown": "Результат отправки неизвестен — проверить вручную",
    "cancelled": "Больше не требуется",
}
ORDER_LABELS = {
    "new": "Новый",
    "payment_pending": "Ожидает оплату",
    "payment_failed": "Оплата не завершена",
    "paid": "Оплачен",
    "refund_failed": "Ошибка возврата",
    "refund_processing": "Возврат обрабатывается",
    "refunded": "Возвращён",
}


def now_utc():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class CheckoutConflict(ValueError):
    pass


class DeliveryRejected(RuntimeError):
    """Известно, что SMTP не принял письмо; повтор допустим."""


class DeliveryUnknown(RuntimeError):
    """Принятие SMTP не подтверждено; автоматически повторять нельзя."""


def issue_checkout_key(slug, config):
    serializer = URLSafeTimedSerializer(config["SECRET_KEY"], salt="st8dom-order-checkout-v1")
    return serializer.dumps({"slug": slug, "nonce": secrets.token_hex(24)})


def checkout_request_key(value, slug, config):
    # Совместимость с уже открытыми до обновления формами. В новых формах ключ
    # обязателен для защиты от двойного клика; старую страницу надо обновить.
    if not value:
        return secrets.token_hex(24)
    serializer = URLSafeTimedSerializer(config["SECRET_KEY"], salt="st8dom-order-checkout-v1")
    try:
        data = serializer.loads(value, max_age=3600)
    except (BadSignature, SignatureExpired) as exc:
        raise ValueError("Обновите страницу заказа и повторите оформление.") from exc
    if not isinstance(data, dict) or data.get("slug") != slug:
        raise ValueError("Неверная форма заказа.")
    nonce = data.get("nonce")
    if not isinstance(nonce, str) or len(nonce) != 48:
        raise ValueError("Неверная форма заказа.")
    return nonce


def create_checkout(product, data, config, request_key):
    fingerprint = hashlib.sha256(json.dumps(
        {"slug": product["slug"], **data}, sort_keys=True, ensure_ascii=False,
    ).encode("utf-8")).hexdigest()

    def existing_result(checkout):
        if checkout.request_hash != fingerprint:
            raise CheckoutConflict("Эта форма уже отправлена с другими данными. Обновите страницу.")
        return db.session.get(Order, checkout.order_id), checkout

    previous = OrderCheckout.query.filter_by(request_key=request_key).first()
    if previous:
        return existing_result(previous)
    order = Order(
        product_slug=product["slug"], product_name=product["name"],
        amount=product["price"], email=data["email"], name=data["name"] or None,
        status="payment_pending",
    )
    db.session.add(order)
    db.session.flush()
    checkout = OrderCheckout(
        order_id=order.id, request_key=request_key, request_hash=fingerprint,
        payment_token=secrets.token_urlsafe(32),
        test_mode=bool(config.get("ROBOKASSA_TEST_MODE")),
        payment_object=product.get("payment_object", "service"),
        contact=data["contact"], comment=data["comment"],
    )
    db.session.add(checkout)
    db.session.add(OrderNotification(order_id=order.id, kind="payment_link"))
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        # Два POST могли одновременно проверить отсутствие одного ключа.
        previous = OrderCheckout.query.filter_by(request_key=request_key).first()
        if previous is None:
            raise
        return existing_result(previous)
    return order, checkout


def config_for_order(order_id, config):
    checkout = db.session.get(OrderCheckout, order_id)
    result = dict(config)
    if checkout:
        result["ROBOKASSA_TEST_MODE"] = checkout.test_mode
    return result


def saved_product(order, checkout):
    return {
        "name": order.product_name, "price": order.amount,
        "price_label": f"{order.amount:.2f} ₽",
        "payment_object": checkout.payment_object,
    }


def payment_link(checkout, config):
    origin = (config.get("SITE_URL") or "").rstrip("/")
    parsed = urlsplit(origin)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("SITE_URL must be a canonical HTTPS URL")
    return f"{origin}/orders/pay/{checkout.payment_token}/"


def smtp_ready(config):
    tls = bool(config.get("SMTP_USE_TLS", True))
    ssl_enabled = bool(config.get("SMTP_USE_SSL"))
    return bool(
        config.get("ORDER_EMAIL_ENABLED")
        and config.get("SMTP_HOST") and config.get("SMTP_USERNAME")
        and config.get("SMTP_PASSWORD")
        and (config.get("SMTP_FROM") or config.get("SMTP_USERNAME"))
        and tls != ssl_enabled
    )


def send_order_email(order, checkout, notification, config):
    """SMTP accept != доставка во входящие. Не выводит адреса/секреты в журнал."""
    sender = (config.get("SMTP_FROM") or config["SMTP_USERNAME"]).strip()
    mail = EmailMessage()
    prefix = "[ТЕСТ] " if checkout.test_mode else ""
    mail["Subject"] = prefix + (
        f"Ссылка для оплаты заказа №{order.id} — ДИС"
        if notification.kind == "payment_link" else f"Оплата заказа №{order.id} подтверждена — ДИС"
    )
    mail["From"] = sender
    mail["To"] = order.email
    mail["Reply-To"] = sender
    # Стабильный Message-ID помогает почтовым системам распознать повтор,
    # но сам по себе не является гарантией доставки ровно один раз.
    domain = sender.rsplit("@", 1)[-1]
    mail["Message-ID"] = f"<st8dom-order-{order.id}-{notification.kind}@{domain}>"
    greeting = f"Здравствуйте, {order.name}!" if order.name else "Здравствуйте!"
    body = [greeting, "", f"Заказ №{order.id}: {order.product_name}.", f"Сумма: {order.amount:.2f} ₽."]
    if checkout.test_mode:
        body += ["Это проверка в тестовом режиме Robokassa, без реального списания."]
    if notification.kind == "payment_link":
        body += ["", "Мы получили ваш заказ. Для оплаты откройте ссылку:", payment_link(checkout, config),
                 "", "После подтверждения оплаты свяжемся с вами для уточнения задачи."]
    else:
        body += ["", "Robokassa подтвердила оплату. Свяжемся с вами для уточнения исходных данных."]
    body += ["", "Если у вас есть вопросы, ответьте на это письмо.", "", "Дмитрий Степанов", config["SITE_URL"]]
    mail.set_content("\n".join(body))

    smtp = None
    data_started = False
    try:
        smtp_type = smtplib.SMTP_SSL if config.get("SMTP_USE_SSL") else smtplib.SMTP
        tls_options = {"context": ssl.create_default_context()} if config.get("SMTP_USE_SSL") else {}
        smtp = smtp_type(config["SMTP_HOST"], int(config["SMTP_PORT"]), timeout=10, **tls_options)
        smtp.ehlo()
        if config.get("SMTP_USE_TLS", True) and not config.get("SMTP_USE_SSL"):
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo()
        smtp.login(config["SMTP_USERNAME"], config["SMTP_PASSWORD"])
        data_started = True
        refused = smtp.send_message(mail)
        if refused:
            raise DeliveryRejected("smtp_recipient_rejected")
    except (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused, smtplib.SMTPDataError) as exc:
        raise DeliveryRejected(type(exc).__name__) from None
    except (OSError, smtplib.SMTPException) as exc:
        failure = DeliveryUnknown if data_started else DeliveryRejected
        raise failure(type(exc).__name__) from None
    finally:
        if smtp is not None:
            try:
                smtp.quit()
            except (OSError, smtplib.SMTPException):
                # Ошибка QUIT не отменяет уже полученный положительный SMTP-ответ.
                try:
                    smtp.close()
                except (OSError, smtplib.SMTPException):
                    pass


def process_notifications(config, *, limit=20):
    now = now_utc()
    result = dict(sent=0, failed=0, unknown=0, cancelled=0, skipped=0)
    # После аварии нельзя знать, получил ли SMTP письмо до остановки процесса.
    stale = OrderNotification.query.filter(
        OrderNotification.status == "sending",
        OrderNotification.attempted_at < now - timedelta(minutes=15),
    ).update({"status": "unknown", "last_error": "worker_interrupted"}, synchronize_session=False)
    db.session.commit()
    result["unknown"] += stale
    if not smtp_ready(config):
        result["skipped"] = 1
        return result
    ids = [row.id for row in OrderNotification.query.filter(
        OrderNotification.status == "pending", OrderNotification.available_at <= now,
    ).order_by(OrderNotification.id).limit(max(1, min(int(limit), 100))).all()]
    for notice_id in ids:
        # Короткий атомарный захват: несколько воркеров не отправляют одно событие.
        claimed = OrderNotification.query.filter(
            OrderNotification.id == notice_id,
            OrderNotification.status == "pending",
            OrderNotification.available_at <= now_utc(),
            OrderNotification.attempts < 3,
        ).update({
            "status": "sending", "attempted_at": now_utc(),
            "attempts": OrderNotification.attempts + 1, "last_error": None,
        }, synchronize_session=False)
        db.session.commit()
        if not claimed:
            continue
        db.session.expire_all()
        notice = db.session.get(OrderNotification, notice_id)
        order = db.session.get(Order, notice.order_id)
        checkout = db.session.get(OrderCheckout, notice.order_id)
        if not order or not checkout:
            notice.status, notice.last_error = "failed", "order_snapshot_missing"
            db.session.commit()
            result["failed"] += 1
            continue
        if notice.kind == "payment_link" and order.status not in INITIAL_PAYMENT_STATES:
            notice.status = "cancelled"
            db.session.commit()
            result["cancelled"] += 1
            continue
        if notice.kind == "payment_received" and order.status != "paid":
            # Пока письмо ожидало обработчика, заказ могли вернуть/закрыть.
            notice.status, notice.last_error = "cancelled", "order_state_changed"
            db.session.commit()
            result["cancelled"] += 1
            continue
        if notice.kind == "payment_link" and checkout.test_mode != bool(config.get("ROBOKASSA_TEST_MODE")):
            notice.status, notice.last_error = "failed", "payment_mode_changed"
            db.session.commit()
            result["failed"] += 1
            continue
        # Ограничение автоматических писем на произвольный адрес из публичной формы.
        day_start = now_utc() - timedelta(days=1)
        delivered = OrderNotification.query.filter(
            OrderNotification.id != notice.id,
            OrderNotification.status.in_(["sent", "sending", "unknown"]),
            OrderNotification.attempted_at >= day_start,
        )
        recipient_count = delivered.join(Order, Order.id == OrderNotification.order_id).filter(Order.email == order.email).count()
        if delivered.count() >= 100 or recipient_count >= 6:
            notice.status, notice.last_error = "pending", "daily_mail_limit"
            notice.available_at = now_utc() + timedelta(hours=1)
            # Лимит не является попыткой SMTP.
            notice.attempts -= 1
            db.session.commit()
            result["skipped"] += 1
            continue
        try:
            send_order_email(order, checkout, notice, config)
        except DeliveryRejected as exc:
            notice.status = "pending" if notice.attempts < 3 else "failed"
            notice.last_error = str(exc)[:80]
            notice.available_at = now_utc() + timedelta(minutes=5 * notice.attempts)
            result["failed"] += 1
        except Exception as exc:
            # Включая неожиданный сбой после начала внешнего действия.
            notice.status, notice.last_error = "unknown", type(exc).__name__
            result["unknown"] += 1
        else:
            notice.status, notice.last_error, notice.sent_at = "sent", None, now_utc()
            result["sent"] += 1
        # Если commit упадёт после SMTP, запись останется sending и будет
        # переведена в unknown; повторной отправки автоматически не будет.
        db.session.commit()
        logger.info("Заказ #%s: уведомление %s, результат %s", order.id, notice.kind, notice.status)
    return result
