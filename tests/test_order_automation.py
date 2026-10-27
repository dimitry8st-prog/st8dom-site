"""Order automation regressions; all identities and external services are synthetic."""

import hashlib
import json
import smtplib
import ssl
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from html.parser import HTMLParser
from urllib.parse import unquote

import pytest


class Inputs(HTMLParser):
    def __init__(self, body):
        super().__init__()
        self.fields = {}
        self.feed(body)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "input" and attrs.get("name"):
            self.fields[attrs["name"]] = attrs.get("value", "")


@pytest.fixture()
def automation_app(tmp_path, monkeypatch):
    import app as app_module
    import config
    import requests
    from extensions import db

    monkeypatch.setenv("FLASK_ENV", "development")
    settings = {
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'orders.sqlite'}",
        "SECRET_KEY": "synthetic-order-automation-signing-key",
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "SITE_URL": "https://portal.example",
        "ROBOKASSA_MERCHANT_LOGIN": "synthetic-shop",
        "ROBOKASSA_TEST_MODE": False,
        "ROBOKASSA_PASSWORD1": "synthetic-live-first",
        "ROBOKASSA_PASSWORD2": "synthetic-live-second",
        "ROBOKASSA_TEST_PASSWORD1": "synthetic-test-first",
        "ROBOKASSA_TEST_PASSWORD2": "synthetic-test-second",
        "ORDER_EMAIL_ENABLED": True,
        "SMTP_HOST": "smtp.example",
        "SMTP_PORT": 587,
        "SMTP_USERNAME": "sender@example.com",
        "SMTP_PASSWORD": "synthetic-application-password",
        "SMTP_FROM": "sender@example.com",
        "SMTP_USE_TLS": True,
    }
    for key, value in settings.items():
        monkeypatch.setattr(config.Config, key, value, raising=False)

    def no_network(*args, **kwargs):
        raise AssertionError("A regression test attempted to contact an external service")

    monkeypatch.setattr(requests.sessions.Session, "request", no_network)
    monkeypatch.setattr(smtplib, "SMTP", no_network)
    monkeypatch.setattr(smtplib, "SMTP_SSL", no_network)
    application = app_module.create_app()
    application.config.update(settings)
    with application.app_context():
        yield application
        db.session.remove()
        db.drop_all()
        db.engine.dispose()


@pytest.fixture()
def order_client(automation_app, tmp_path):
    with automation_app.test_client() as client:
        # Each test is a different synthetic visitor; the production limiter is
        # process-wide and must not accumulate unrelated test requests.
        visitor = hashlib.sha256(str(tmp_path).encode()).digest()
        client.environ_base["REMOTE_ADDR"] = f"198.18.{visitor[0]}.{visitor[1]}"
        yield client


def checkout(client, app, *, key=None, email="buyer@example.com", **overrides):
    import order_automation
    from app import PRODUCTS_BY_SLUG
    from models import Order, OrderCheckout

    slug = next(slug for slug, item in PRODUCTS_BY_SLUG.items()
                if item.get("sellable") and item.get("price"))
    data = {
        "checkout_key": key or order_automation.issue_checkout_key(slug, app.config),
        "name": "Тестовый Покупатель",
        "email": email,
        "contact": "@synthetic_buyer",
        "comment": "Нужна консультация по вымышленному проекту.",
    }
    data.update(overrides)
    response = client.post(f"/products/{slug}/checkout/", data=data)
    order = Order.query.filter_by(email=email).order_by(Order.id.desc()).first()
    snapshot = OrderCheckout.query.filter_by(order_id=order.id).one() if order else None
    return response, order, snapshot, data


def result(client, app, order, *, amount=None, password=None):
    amount = amount if amount is not None else f"{order.amount:.6f}"
    password = password or app.config["ROBOKASSA_PASSWORD2"]
    signature = hashlib.md5(f"{amount}:{order.id}:{password}".encode()).hexdigest()
    return client.post("/payments/robokassa/result/", data={
        "OutSum": amount, "InvId": str(order.id), "SignatureValue": signature,
    })


def test_checkout_replay_preserves_one_invoice_and_one_queued_email(order_client, automation_app):
    from app import PRODUCTS_BY_SLUG
    from models import Order, OrderNotification

    response, order, snapshot, data = checkout(order_client, automation_app)
    assert response.status_code == 200
    fields = Inputs(response.get_data(as_text=True)).fields
    assert fields["InvId"] == str(order.id)
    assert snapshot.contact == data["contact"]
    assert snapshot.comment == data["comment"]
    assert snapshot.test_mode is False
    again = order_client.post(f"/products/{order.product_slug}/checkout/", data=data)
    assert again.status_code == 200
    assert Order.query.count() == 1
    assert OrderNotification.query.filter_by(order_id=order.id, kind="payment_link").count() == 1
    assert OrderNotification.query.one().attempts == 0
    assert order.amount == Decimal(str(PRODUCTS_BY_SLUG[order.product_slug]["price"]))


@pytest.mark.parametrize("changed", [
    {"email": "someone-else@example.com"},
    {"contact": "@different_synthetic_contact"},
    {"comment": "Другая задача"},
])
def test_same_checkout_key_with_changed_request_is_conflict(order_client, automation_app, changed):
    from models import Order, OrderNotification

    _, order, _, data = checkout(order_client, automation_app)
    data.update(changed)
    response = order_client.post(f"/products/{order.product_slug}/checkout/", data=data)
    assert response.status_code == 409
    assert Order.query.count() == 1
    assert OrderNotification.query.count() == 1


def test_invalid_checkout_key_creates_no_order(order_client, automation_app):
    from models import Order, OrderNotification

    response, _, _, _ = checkout(order_client, automation_app, key="forged-checkout-key")
    assert response.status_code == 400
    assert Order.query.count() == 0
    assert OrderNotification.query.count() == 0


@pytest.mark.parametrize("invalid_kind", ["expired", "wrong_product"])
def test_signed_checkout_key_is_bound_to_product_and_lifetime(order_client, automation_app, monkeypatch,
                                                            invalid_kind):
    import order_automation
    from app import PRODUCTS_BY_SLUG
    from itsdangerous import TimestampSigner
    from models import Order, OrderNotification

    slug = next(slug for slug, item in PRODUCTS_BY_SLUG.items()
                if item.get("sellable") and item.get("price"))
    if invalid_kind == "expired":
        old_timestamp = int(datetime.now(timezone.utc).timestamp()) - 3700
        with monkeypatch.context() as frozen:
            frozen.setattr(TimestampSigner, "get_timestamp", lambda self: old_timestamp)
            key = order_automation.issue_checkout_key(slug, automation_app.config)
    else:
        key = order_automation.issue_checkout_key("other-synthetic-product", automation_app.config)
    response, _, _, _ = checkout(order_client, automation_app, key=key)
    assert response.status_code == 400
    assert Order.query.count() == 0
    assert OrderNotification.query.count() == 0


def test_client_cannot_override_catalog_payment_amount(order_client, automation_app):
    from app import PRODUCTS_BY_SLUG

    response, order, _, _ = checkout(order_client, automation_app, amount="0.01", price="0.01")
    assert response.status_code == 200
    fields = Inputs(response.get_data(as_text=True)).fields
    assert Decimal(fields["OutSum"]) == Decimal(str(PRODUCTS_BY_SLUG[order.product_slug]["price"]))
    assert Decimal(fields["OutSum"]) != Decimal("0.01")


def test_link_uses_saved_price_and_name_after_catalog_change(order_client, automation_app, monkeypatch):
    import order_automation
    from app import PRODUCTS_BY_SLUG
    from models import Order

    _, order, snapshot, _ = checkout(order_client, automation_app)
    saved_name, saved_amount = order.product_name, order.amount
    product = PRODUCTS_BY_SLUG[order.product_slug]
    monkeypatch.setitem(product, "name", "Changed catalog name")
    monkeypatch.setitem(product, "price", 1)
    url = order_automation.payment_link(snapshot, automation_app.config)
    assert url == f"https://portal.example/orders/pay/{snapshot.payment_token}/"
    response = order_client.get(url)
    assert response.status_code == 200
    fields = Inputs(response.get_data(as_text=True)).fields
    assert fields["OutSum"] == f"{saved_amount:.2f}"
    assert fields["InvId"] == str(order.id)
    receipt = json.loads(unquote(fields["Receipt"]))
    assert receipt["items"][0]["name"] == saved_name[:128]
    assert Decimal(str(receipt["items"][0]["sum"])) == saved_amount
    assert Order.query.count() == 1
    assert "form-action 'self' https://auth.robokassa.ru" in response.headers["Content-Security-Policy"]
    other_policy = order_client.get("/products/").headers["Content-Security-Policy"]
    assert "form-action 'self';" in other_policy


def test_unknown_payment_token_and_mode_switch_do_not_create_orders(order_client, automation_app, monkeypatch):
    from models import Order

    assert order_client.get("/orders/pay/nonexistent-synthetic-token/").status_code == 404
    _, _, snapshot, _ = checkout(order_client, automation_app)
    monkeypatch.setitem(automation_app.config, "ROBOKASSA_TEST_MODE", True)
    response = order_client.get(f"/orders/pay/{snapshot.payment_token}/")
    assert response.status_code == 409
    assert Order.query.count() == 1


def test_signed_payment_callback_is_idempotent_and_queues_one_receipt_notice(order_client, automation_app):
    import order_automation
    from extensions import db
    from models import OrderNotification

    _, order, snapshot, _ = checkout(order_client, automation_app)
    first = result(order_client, automation_app, order)
    assert first.status_code == 200
    assert first.get_data(as_text=True) == f"OK{order.id}"
    db.session.refresh(order)
    assert order.status == "paid"
    paid_at = order.paid_at
    assert paid_at is not None
    assert result(order_client, automation_app, order).status_code == 200
    db.session.refresh(order)
    assert order.paid_at == paid_at
    assert OrderNotification.query.filter_by(order_id=order.id, kind="payment_received").count() == 1
    # Reading an already-paid payment link must not expose another payment form.
    response = order_client.get(order_automation.payment_link(snapshot, automation_app.config))
    assert response.status_code == 200
    assert "SignatureValue" not in Inputs(response.get_data(as_text=True)).fields


@pytest.mark.parametrize("status", ["refund_processing", "refunded", "refund_failed"])
def test_payment_callback_replay_preserves_refund_state(order_client, automation_app, status):
    from extensions import db
    from models import OrderNotification

    _, order, _, _ = checkout(order_client, automation_app)
    order.status = status
    order.paid_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.session.commit()
    response = result(order_client, automation_app, order)
    assert response.status_code == 200
    db.session.refresh(order)
    assert order.status == status
    assert OrderNotification.query.filter_by(order_id=order.id, kind="payment_received").count() == 0


def test_callback_uses_persisted_mode_not_current_global_mode(order_client, automation_app, monkeypatch):
    from extensions import db

    _, order, _, _ = checkout(order_client, automation_app)
    monkeypatch.setitem(automation_app.config, "ROBOKASSA_TEST_MODE", True)
    wrong = result(order_client, automation_app, order,
                   password=automation_app.config["ROBOKASSA_TEST_PASSWORD2"])
    assert wrong.status_code == 400
    db.session.refresh(order)
    assert order.status == "payment_pending"
    assert result(order_client, automation_app, order).status_code == 200
    db.session.refresh(order)
    assert order.status == "paid"


@pytest.mark.parametrize("amount", ["0.01", "NaN", "sNaN", "Infinity", "not-money"])
def test_invalid_callback_amount_cannot_mark_paid(order_client, automation_app, amount):
    from extensions import db
    from models import OrderNotification

    _, order, _, _ = checkout(order_client, automation_app)
    response = result(order_client, automation_app, order, amount=amount)
    assert response.status_code == 400
    db.session.refresh(order)
    assert order.status == "payment_pending"
    assert order.paid_at is None
    assert OrderNotification.query.filter_by(kind="payment_received").count() == 0


def test_browser_redirects_do_not_change_payment_or_disclose_order(order_client, automation_app):
    from extensions import db

    _, order, _, _ = checkout(order_client, automation_app)
    for path in ("fail", "success"):
        response = order_client.get(f"/payments/robokassa/{path}/?InvId={order.id}")
        assert response.status_code == 200
        assert order.product_name not in response.get_data(as_text=True)
        assert order.email not in response.get_data(as_text=True)
        db.session.refresh(order)
        assert order.status == "payment_pending"
        assert order.paid_at is None


def test_notification_worker_sends_once_without_creating_payment(order_client, automation_app, monkeypatch):
    import order_automation
    from models import Order, OrderNotification

    _, order, _, _ = checkout(order_client, automation_app)
    sent = []
    monkeypatch.setattr(order_automation, "send_order_email",
                        lambda order, checkout, notification, config: sent.append((order.id, notification.kind)))
    stats = order_automation.process_notifications(automation_app.config)
    assert stats["sent"] == 1
    assert sent == [(order.id, "payment_link")]
    notification = OrderNotification.query.one()
    assert notification.status == "sent"
    assert notification.sent_at is not None
    assert notification.attempts == 1
    order_automation.process_notifications(automation_app.config)
    assert sent == [(order.id, "payment_link")]
    assert Order.query.count() == 1
    assert order.status == "payment_pending"


@pytest.mark.parametrize("setting,value", [("SMTP_PASSWORD", ""), ("ORDER_EMAIL_ENABLED", False)])
def test_disabled_mail_leaves_events_unclaimed(order_client, automation_app, monkeypatch, setting, value):
    import order_automation
    from models import OrderNotification

    checkout(order_client, automation_app)
    monkeypatch.setitem(automation_app.config, setting, value)
    order_automation.process_notifications(automation_app.config)
    notification = OrderNotification.query.one()
    assert notification.status == "pending"
    assert notification.attempts == 0
    assert notification.attempted_at is None


def test_known_smtp_rejection_retries_at_most_three_times(order_client, automation_app, monkeypatch):
    import order_automation
    from extensions import db
    from models import OrderNotification

    checkout(order_client, automation_app)
    calls = []

    def reject(*args):
        calls.append(1)
        raise order_automation.DeliveryRejected("synthetic SMTP rejection before acceptance")

    monkeypatch.setattr(order_automation, "send_order_email", reject)
    order_automation.process_notifications(automation_app.config)
    notification = OrderNotification.query.one()
    assert notification.status == "pending"
    assert notification.attempts == 1
    assert notification.available_at > datetime.now(timezone.utc).replace(tzinfo=None)
    # The next worker pass must respect backoff, not immediately resend.
    order_automation.process_notifications(automation_app.config)
    assert len(calls) == 1
    for expected in (2, 3):
        notification.available_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1)
        db.session.commit()
        order_automation.process_notifications(automation_app.config)
        db.session.refresh(notification)
        assert notification.attempts == expected
    assert notification.status == "failed"
    order_automation.process_notifications(automation_app.config)
    assert len(calls) == 3


def test_ambiguous_mail_outcome_is_not_retried(order_client, automation_app, monkeypatch):
    import order_automation
    from models import OrderNotification

    checkout(order_client, automation_app)
    calls = []

    def ambiguous(*args):
        calls.append(1)
        raise order_automation.DeliveryUnknown("synthetic timeout after DATA")

    monkeypatch.setattr(order_automation, "send_order_email", ambiguous)
    order_automation.process_notifications(automation_app.config)
    notification = OrderNotification.query.one()
    assert notification.status == "unknown"
    assert notification.attempts == 1
    order_automation.process_notifications(automation_app.config)
    assert len(calls) == 1


@pytest.mark.parametrize("interleaving", ["deferred", "attempt_limit"])
def test_worker_rechecks_due_time_and_attempt_limit_when_claiming_candidate(
        order_client, automation_app, monkeypatch, interleaving):
    """A candidate list can become stale after another worker's safe failure."""
    import order_automation
    from extensions import db
    from models import OrderNotification
    from sqlalchemy.orm import Query

    checkout(order_client, automation_app)
    notification = OrderNotification.query.one()
    notice_id = notification.id
    original_update = Query.update
    intervened = []
    sent = []

    def other_worker_finishes_before_claim(query, values, *args, **kwargs):
        if values.get("status") == "sending" and not intervened:
            intervened.append(True)
            # Worker A has already listed this due ID. Simulate worker B
            # returning it to pending with a future retry or exhausted attempts.
            next_time = datetime.now(timezone.utc).replace(tzinfo=None)
            next_time += timedelta(hours=1) if interleaving == "deferred" else timedelta(seconds=-1)
            original_update(OrderNotification.query.filter_by(id=notice_id), {
                "status": "pending",
                "attempts": 1 if interleaving == "deferred" else 3,
                "available_at": next_time,
                "last_error": "synthetic known pre-DATA failure in another worker",
            }, synchronize_session=False)
            db.session.commit()
            db.session.expire_all()
        return original_update(query, values, *args, **kwargs)

    monkeypatch.setattr(Query, "update", other_worker_finishes_before_claim)
    monkeypatch.setattr(order_automation, "send_order_email",
                        lambda *args: sent.append(True))
    order_automation.process_notifications(automation_app.config)
    assert intervened == [True]
    assert sent == []
    db.session.refresh(notification)
    assert notification.status == "pending"
    assert notification.attempts == (1 if interleaving == "deferred" else 3)
    if interleaving == "deferred":
        assert notification.available_at > datetime.now(timezone.utc).replace(tzinfo=None)


@pytest.mark.parametrize("tls,ssl_enabled", [(False, False), (True, True)])
def test_unsafe_or_conflicting_transport_config_leaves_mail_unclaimed(
        order_client, automation_app, monkeypatch, tls, ssl_enabled):
    import order_automation
    from models import OrderNotification

    checkout(order_client, automation_app)
    monkeypatch.setitem(automation_app.config, "SMTP_USE_TLS", tls)
    monkeypatch.setitem(automation_app.config, "SMTP_USE_SSL", ssl_enabled)
    stats = order_automation.process_notifications(automation_app.config)
    assert stats["sent"] == 0
    assert stats["skipped"] >= 1
    notification = OrderNotification.query.one()
    assert notification.status == "pending"
    assert notification.attempts == 0
    assert notification.attempted_at is None


def test_paid_event_cancels_stale_payment_link_notice(order_client, automation_app, monkeypatch):
    import order_automation
    from models import OrderNotification

    _, order, _, _ = checkout(order_client, automation_app)
    assert result(order_client, automation_app, order).status_code == 200
    sent = []
    monkeypatch.setattr(order_automation, "send_order_email",
                        lambda order, checkout, notification, config: sent.append(notification.kind))
    order_automation.process_notifications(automation_app.config)
    assert sent == ["payment_received"]
    assert OrderNotification.query.filter_by(kind="payment_link").one().status == "cancelled"
    assert OrderNotification.query.filter_by(kind="payment_received").one().status == "sent"


class FakeSMTP:
    """SMTP stand-in supporting explicit envelope/DATA and send_message flows."""

    login_error = None
    data_error = None
    quit_error = None
    messages = None

    def __init__(self, *args, **kwargs):
        self.messages = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.quit()

    def ehlo(self):
        return 250, b"synthetic greeting"

    def starttls(self, *args, **kwargs):
        return 220, b"synthetic TLS"

    def login(self, *args, **kwargs):
        if self.login_error:
            raise self.login_error
        return 235, b"synthetic authenticated"

    def mail(self, *args, **kwargs):
        return 250, b"sender accepted"

    def rcpt(self, *args, **kwargs):
        return 250, b"recipient accepted"

    def data(self, message):
        if self.data_error:
            raise self.data_error
        self.messages.append(message)
        return 250, b"message accepted"

    def sendmail(self, sender, recipients, message, **kwargs):
        self.data(message)
        return {}

    def send_message(self, message, **kwargs):
        return self.sendmail(message["From"], [message["To"]], message.as_bytes())

    def quit(self):
        if self.quit_error:
            raise self.quit_error
        return 221, b"bye"

    def close(self):
        pass


@pytest.mark.parametrize("phase,exception_type", [
    ("login", "DeliveryRejected"),
    ("data_disconnect", "DeliveryUnknown"),
    ("data_refusal", "DeliveryRejected"),
])
def test_smtp_delivery_classifies_known_and_unknown_outcomes(order_client, automation_app, monkeypatch,
                                                          phase, exception_type):
    import order_automation
    from models import OrderNotification

    _, order, snapshot, _ = checkout(order_client, automation_app)
    smtp = FakeSMTP()
    if phase == "login":
        smtp.login_error = smtplib.SMTPAuthenticationError(535, b"synthetic auth failure")
    elif phase == "data_disconnect":
        smtp.data_error = smtplib.SMTPServerDisconnected("synthetic DATA disconnect")
    else:
        smtp.data_error = smtplib.SMTPDataError(451, b"synthetic DATA refusal")
    monkeypatch.setattr(smtplib, "SMTP", lambda *args, **kwargs: smtp)
    with pytest.raises(getattr(order_automation, exception_type)):
        order_automation.send_order_email(order, snapshot, OrderNotification.query.one(), automation_app.config)


def test_smtp_accepted_message_survives_quit_failure(order_client, automation_app, monkeypatch):
    import order_automation
    from models import OrderNotification

    _, order, snapshot, _ = checkout(order_client, automation_app)
    smtp = FakeSMTP()
    smtp.quit_error = smtplib.SMTPServerDisconnected("synthetic failure after acceptance")
    monkeypatch.setattr(smtplib, "SMTP", lambda *args, **kwargs: smtp)
    order_automation.send_order_email(order, snapshot, OrderNotification.query.one(), automation_app.config)
    assert len(smtp.messages) == 1
    message = smtp.messages[0]
    if isinstance(message, bytes):
        message = message.decode("utf-8")
    assert "buyer@example.com" in message


@pytest.mark.parametrize("transport", ["ssl", "starttls"])
def test_smtp_transport_requires_verified_tls_context(order_client, automation_app, monkeypatch, transport):
    import order_automation
    from models import OrderNotification

    _, order, snapshot, _ = checkout(order_client, automation_app)
    smtp = FakeSMTP()
    contexts = {}
    monkeypatch.setitem(automation_app.config, "SMTP_USE_SSL", transport == "ssl")
    monkeypatch.setitem(automation_app.config, "SMTP_USE_TLS", transport == "starttls")
    monkeypatch.setitem(automation_app.config, "SMTP_PORT", 465 if transport == "ssl" else 587)

    def ssl_connection(*args, context, **kwargs):
        contexts["ssl"] = context
        return smtp

    def start_tls(*args, context, **kwargs):
        contexts["starttls"] = context
        return 220, b"synthetic encrypted connection"

    smtp.starttls = start_tls
    if transport == "ssl":
        monkeypatch.setattr(smtplib, "SMTP_SSL", ssl_connection)
    else:
        monkeypatch.setattr(smtplib, "SMTP", lambda *args, **kwargs: smtp)
    order_automation.send_order_email(order, snapshot, OrderNotification.query.one(), automation_app.config)
    assert list(contexts) == [transport]
    context = contexts[transport]
    assert isinstance(context, ssl.SSLContext)
    assert context.check_hostname is True
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert len(smtp.messages) == 1

