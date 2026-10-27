"""Scoped order API regressions. No real credentials, messages or payments."""

import json
from decimal import Decimal

import pytest


TOKEN = "synthetic-n8n-order-api-token-32-characters"
REQUEST_ID = "nns09-00000000000000000001"
HEADERS = {"Authorization": "Bearer " + TOKEN}


@pytest.fixture()
def api_app(tmp_path, monkeypatch):
    import config
    import requests
    import smtplib
    from app import create_app
    from extensions import db

    monkeypatch.setenv("FLASK_ENV", "development")
    settings = {
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'n8n-orders.sqlite'}",
        "TESTING": True, "WTF_CSRF_ENABLED": True,
        "SECRET_KEY": "synthetic-csrf-signing-key",
        "SITE_URL": "https://portal.example",
        "N8N_ORDERS_API_TOKEN": TOKEN,
        "ROBOKASSA_MERCHANT_LOGIN": "synthetic-shop",
        "ROBOKASSA_TEST_MODE": False,
        "ROBOKASSA_PASSWORD1": "synthetic-live-first",
        "ROBOKASSA_PASSWORD2": "synthetic-live-second",
        "ORDER_EMAIL_ENABLED": True,
    }
    for key, value in settings.items():
        monkeypatch.setattr(config.Config, key, value, raising=False)

    def no_network(*args, **kwargs):
        raise AssertionError("An API regression attempted external communication")

    monkeypatch.setattr(requests.sessions.Session, "request", no_network)
    monkeypatch.setattr(smtplib, "SMTP", no_network)
    monkeypatch.setattr(smtplib, "SMTP_SSL", no_network)
    application = create_app()
    application.config.update(settings)
    with application.app_context():
        yield application
        db.session.remove()
        db.drop_all()
        db.engine.dispose()


@pytest.fixture()
def client(api_app):
    return api_app.test_client()


@pytest.fixture()
def payload():
    return {
        "request_id": REQUEST_ID, "product_slug": "express-review", "amount": "4900.00",
        "name": "Синтетический Покупатель", "email": "buyer@example.com",
        "contact": "@synthetic-buyer", "comment": "Вымышленная консультация.",
        "analysis": {
            "client_name": "Синтетический Покупатель", "request_type": "Консультация",
            "request_summary": "Нужно обсудить вымышленный процесс.",
            "payment_description": "Экспресс-разбор", "amount": "4900.00", "priority": "normal",
        },
    }


def create(client, payload, headers=None):
    return client.post("/api/automation/orders/", json=payload,
                       headers=HEADERS if headers is None else headers)


def test_create_is_csrf_exempt_but_only_with_explicit_bearer(client, payload):
    from models import Order, OrderCheckout, OrderNotification

    response = create(client, payload)
    assert response.status_code == 200
    data = response.get_json()
    assert data["request_id"] == REQUEST_ID
    assert data["order_id"] == Order.query.one().id
    assert data["amount"] == "4900.00"
    assert data["status"] == "payment_pending"
    assert data["notification_status"] == "not_queued"
    assert data["payment_link"] == f"https://portal.example/orders/pay/{OrderCheckout.query.one().payment_token}/"
    assert OrderNotification.query.count() == 0
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    # The new exemption does not cover the existing browser checkout.
    assert client.post("/products/express-review/checkout/", data={}).status_code == 400


@pytest.mark.parametrize("token,status", [("", 404), ("short", 503)])
def test_disabled_or_misconfigured_token_fails_closed(api_app, client, payload, token, status):
    from models import Order

    api_app.config["N8N_ORDERS_API_TOKEN"] = token
    assert create(client, payload).status_code == status
    assert client.get(f"/api/automation/orders/{REQUEST_ID}/", headers=HEADERS).status_code == status
    assert client.post(f"/api/automation/orders/{REQUEST_ID}/notify/", headers=HEADERS).status_code == status
    assert Order.query.count() == 0


@pytest.mark.parametrize("authorization", [None, "Bearer wrong", "Basic synthetic", "Bearer ", "bearer " + TOKEN])
def test_cookie_or_wrong_authorization_cannot_create(client, payload, authorization):
    from models import Order

    headers = {"Authorization": authorization} if authorization else {}
    with client.session_transaction() as session:
        session["_user_id"] = "1"
    response = create(client, payload, headers=headers)
    assert response.status_code == 401
    assert Order.query.count() == 0


def test_replay_reuses_one_order_and_does_not_queue_mail(client, payload):
    from models import Order, OrderNotification

    first = create(client, payload).get_json()
    second = create(client, payload).get_json()
    assert first == second
    assert Order.query.count() == 1
    assert OrderNotification.query.count() == 0


@pytest.mark.parametrize("field", ["email", "name", "contact", "comment", "analysis"])
def test_changed_request_id_payload_is_conflict(client, payload, field):
    from models import Order, OrderNotification

    assert create(client, payload).status_code == 200
    if field == "analysis":
        payload[field]["request_summary"] = "Изменённая задача"
    else:
        payload[field] = "different@example.com" if field == "email" else "Изменено"
    assert create(client, payload).status_code == 409
    assert Order.query.count() == 1
    assert OrderNotification.query.count() == 0


@pytest.mark.parametrize("amount", ["0.01", "NaN", "Infinity", "-4900", "4.9e3", 4900, None, True])
def test_invalid_amount_is_rejected_before_creating(client, payload, amount):
    from models import Order

    payload["amount"] = amount
    assert create(client, payload).status_code == 400
    assert Order.query.count() == 0


@pytest.mark.parametrize("slug", ["psychologist-landing", "meeting-intelligence", "unknown", None, [], True])
def test_only_two_approved_fixed_price_products(client, payload, slug):
    from models import Order

    payload["product_slug"] = slug
    assert create(client, payload).status_code == 400
    assert Order.query.count() == 0


@pytest.mark.parametrize("mutation", [
    lambda p: p.update({"email": "invalid"}),
    lambda p: p.update({"request_id": "short"}),
    lambda p: p.update({"request_id": "нельзя-кириллицу-0001"}),
    lambda p: p.update({"comment": "x" * 3001}),
    lambda p: p.update({"name": "x" * 121}),
    lambda p: p.update({"contact": "x" * 121}),
    lambda p: p.update({"status": "paid"}),
    lambda p: p.update({"payment_link": "https://attacker.example"}),
    lambda p: p["analysis"].update({"amount": "0.01"}),
    lambda p: p["analysis"].update({"priority": "run_shell"}),
    lambda p: p["analysis"].update({"extra": "do not allow"}),
    lambda p: p["analysis"].pop("request_summary"),
    lambda p: p.update({"analysis": []}),
])
def test_bad_fields_and_model_output_are_rejected(client, payload, mutation):
    from models import Order

    mutation(payload)
    assert create(client, payload).status_code == 400
    assert Order.query.count() == 0


@pytest.mark.parametrize("bad_body", [[], None, "text", 123, {}])
def test_body_must_be_exact_documented_object(client, bad_body):
    from models import Order

    assert client.post("/api/automation/orders/", json=bad_body, headers=HEADERS).status_code == 400
    assert Order.query.count() == 0


def test_large_body_is_bounded(client):
    response = client.post("/api/automation/orders/", data="x" * 24001,
                           content_type="application/json", headers=HEADERS)
    assert response.status_code == 413


def test_unknown_content_length_body_is_bounded(client):
    import io
    response = client.open("/api/automation/orders/", method="POST", headers=HEADERS,
                           content_type="application/json", environ_overrides={
                               "wsgi.input": io.BytesIO(b"x" * 24001),
                               "wsgi.input_terminated": True, "CONTENT_LENGTH": "",
                           })
    assert response.status_code == 413


def test_unauthorized_probes_do_not_spend_authenticated_quota(client, payload):
    for _ in range(65):
        assert create(client, payload, headers={}).status_code == 401
    assert create(client, payload).status_code == 200


@pytest.mark.parametrize("origin", ["http://portal.example", "https://[", "https://portal.example/?bad=1"])
def test_invalid_origin_does_not_save_partial_order(client, api_app, payload, origin):
    from models import Order
    api_app.config["SITE_URL"] = origin
    assert create(client, payload).status_code == 503
    assert Order.query.count() == 0


def test_exact_decimal_and_canonical_analysis_amount(client, payload):
    from models import Order, OrderCheckout

    payload["amount"] = "4900.000000"
    payload["analysis"]["amount"] = "4900"
    assert create(client, payload).status_code == 200
    assert Order.query.one().amount == Decimal("4900.00")
    assert '"amount": "4900.00"' in OrderCheckout.query.one().comment


def test_notify_enqueues_once_after_explicit_step_and_retries_do_not_resend(client, payload):
    from extensions import db
    from models import OrderNotification

    assert create(client, payload).status_code == 200
    url = f"/api/automation/orders/{REQUEST_ID}/notify/"
    first = client.post(url, json={}, headers=HEADERS)
    assert first.status_code == 200
    assert first.get_json()["notification_status"] == "pending"
    notice = OrderNotification.query.one()
    assert notice.attempts == 0
    assert client.post(url, json={}, headers=HEADERS).get_json() == first.get_json()
    assert OrderNotification.query.count() == 1
    for status in ["sending", "sent", "failed", "unknown", "cancelled"]:
        notice.status = status
        notice.attempts = 3
        db.session.commit()
        assert client.post(url, json={}, headers=HEADERS).get_json()["notification_status"] == status
        assert OrderNotification.query.one().attempts == 3


@pytest.mark.parametrize("state", ["paid", "refund_processing", "refund_failed", "refunded"])
def test_notify_of_terminal_order_does_not_create_mail(client, payload, state):
    from extensions import db
    from models import Order, OrderNotification

    assert create(client, payload).status_code == 200
    order = Order.query.one()
    order.status = state
    db.session.commit()
    response = client.post(f"/api/automation/orders/{REQUEST_ID}/notify/", json={}, headers=HEADERS)
    assert response.status_code == 409
    assert Order.query.one().status == state
    assert OrderNotification.query.count() == 0


@pytest.mark.parametrize("bad_body", [{"email": "other@example.com"}, [], None, "not-object"])
def test_notify_cannot_change_recipient(client, payload, bad_body):
    from models import OrderNotification

    assert create(client, payload).status_code == 200
    response = client.post(f"/api/automation/orders/{REQUEST_ID}/notify/", headers=HEADERS,
                           data=json.dumps(bad_body),
                           content_type="application/json")
    # A JSON-null body has bytes, and is rejected; omitted body is allowed below.
    assert response.status_code == 400
    assert OrderNotification.query.count() == 0


def test_get_requires_original_request_id_not_public_order_number(client, payload):
    from models import Order

    original = create(client, payload).get_json()
    assert client.get(f"/api/automation/orders/{REQUEST_ID}/", headers=HEADERS).get_json() == original
    assert client.get(f"/api/automation/orders/{Order.query.one().id}/", headers=HEADERS).status_code == 400
    assert client.get("/api/automation/orders/unknown-000000000000/", headers=HEADERS).status_code == 404


def test_mode_change_rejects_create_get_and_notify(client, api_app, payload):
    from models import Order, OrderNotification

    assert create(client, payload).status_code == 200
    api_app.config["ROBOKASSA_TEST_MODE"] = True
    assert create(client, payload).status_code == 409
    assert client.get(f"/api/automation/orders/{REQUEST_ID}/", headers=HEADERS).status_code == 409
    assert client.post(f"/api/automation/orders/{REQUEST_ID}/notify/", json={}, headers=HEADERS).status_code == 409
    assert Order.query.count() == 1
    assert OrderNotification.query.count() == 0


def test_replay_uses_saved_price_after_catalog_changes(client, payload, monkeypatch):
    from products import PRODUCTS_BY_SLUG

    first = create(client, payload).get_json()
    monkeypatch.setitem(PRODUCTS_BY_SLUG["express-review"], "price", 9900)
    assert create(client, payload).get_json() == first


def test_existing_public_order_cannot_be_addressed_by_its_nonce(client, api_app, payload):
    from extensions import db
    from models import Order, OrderCheckout
    from order_automation import create_checkout
    from products import PRODUCTS_BY_SLUG

    order, snapshot = create_checkout(PRODUCTS_BY_SLUG["express-review"], {
        "email": "browser@example.com", "name": "Browser", "contact": "", "comment": "",
    }, api_app.config, "a" * 48)
    assert client.get(f"/api/automation/orders/{snapshot.request_key}/", headers=HEADERS).status_code == 404
    assert client.post(f"/api/automation/orders/{snapshot.request_key}/notify/", json={}, headers=HEADERS).status_code == 404


def test_api_requests_do_not_count_public_visits(client, payload):
    from models import PortalVisit

    assert create(client, payload).status_code == 200
    assert client.get(f"/api/automation/orders/{REQUEST_ID}/", headers=HEADERS).status_code == 200
    assert PortalVisit.query.count() == 0
