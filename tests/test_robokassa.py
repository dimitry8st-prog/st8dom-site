import hashlib
from types import SimpleNamespace

import pytest

from payments_robokassa import enabled, payment_form, valid_result_signature, valid_success_signature


@pytest.mark.parametrize("bom", [b"", b"\xef\xbb\xbf"])
def test_operation_key_xml_uses_response_bytes(monkeypatch, bom):
    import requests
    import payments_robokassa as robokassa

    response = requests.Response()
    response.status_code = 200
    response.encoding = "ISO-8859-1"
    response._content = bom + (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<Operation xmlns="urn:robokassa"><OpKey>operation-key</OpKey></Operation>'
    ).encode("utf-8")
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return response

    monkeypatch.setattr(robokassa.requests, "get", fake_get)
    config = {"ROBOKASSA_TEST_MODE": False,
              "ROBOKASSA_MERCHANT_LOGIN": "shop", "ROBOKASSA_PASSWORD2": "second"}
    assert robokassa.fetch_op_key(SimpleNamespace(id=7), config) == "operation-key"
    assert calls[0][1]["params"]["Signature"] == hashlib.md5(b"shop:7:second").hexdigest()
    assert calls[0][1]["timeout"] == 15


@pytest.mark.parametrize("test_mode", [True, False])
def test_payment_credentials_are_separate_for_each_mode(test_mode):
    prefix = "ROBOKASSA_TEST_PASSWORD" if test_mode else "ROBOKASSA_PASSWORD"
    config = {"ROBOKASSA_MERCHANT_LOGIN": "shop", "ROBOKASSA_TEST_MODE": test_mode,
              prefix + "1": "first", prefix + "2": "second"}
    assert enabled(config)
    order = SimpleNamespace(id=7, amount=100, email="buyer@example.com")
    product = {"name": "Service", "price": 100}
    fields = payment_form(order, product, config)["fields"]
    assert (fields.get("IsTest") == "1") == test_mode
    # The decoded HTTP form value must be identical to the receipt used in the signature.
    from urllib.parse import parse_qs, urlencode, unquote
    import json
    submitted = {key: values[0] for key, values in parse_qs(urlencode(fields)).items()}
    expected_payment_sign = hashlib.md5(
        f"shop:100.00:7:{submitted['Receipt']}:first".encode()
    ).hexdigest()
    assert submitted["SignatureValue"] == expected_payment_sign
    assert json.loads(unquote(submitted["Receipt"]))["items"][0]["name"] == "Service"
    result_sign = hashlib.md5(b"100.00:7:second").hexdigest()
    success_sign = hashlib.md5(b"100.00:7:first").hexdigest()
    assert valid_result_signature("100.00", "7", result_sign, config)
    assert valid_success_signature("100.00", "7", success_sign, config)
    config["ROBOKASSA_TEST_MODE"] = not test_mode
    assert not enabled(config)
    assert not valid_result_signature("100.00", "7", result_sign, config)
    assert not valid_success_signature("100.00", "7", success_sign, config)
    with pytest.raises(ValueError):
        payment_form(order, product, config)


def test_missing_password_cannot_validate_publicly_computable_signature():
    config = {"ROBOKASSA_TEST_MODE": True}
    signature = hashlib.md5(b"100.00:7:").hexdigest()
    assert not valid_result_signature("100.00", "7", signature, config)
    assert not valid_success_signature("100.00", "7", signature, config)


def test_checkout_form_destination_is_allowed_by_browser_policy(client, monkeypatch):
    from app import app, PRODUCTS_BY_SLUG
    from extensions import db
    from models import Order
    from payments_robokassa import PAY_URL
    from urllib.parse import urlsplit

    for key, value in {
        "ROBOKASSA_MERCHANT_LOGIN": "shop",
        "ROBOKASSA_TEST_MODE": True,
        "ROBOKASSA_TEST_PASSWORD1": "first",
        "ROBOKASSA_TEST_PASSWORD2": "second",
    }.items():
        monkeypatch.setitem(app.config, key, value)
    slug = next(key for key, product in PRODUCTS_BY_SLUG.items()
                if product.get("sellable") and product.get("price"))
    email = "checkout-csp-test@example.com"
    try:
        response = client.post(f"/products/{slug}/checkout/",
                               data={"name": "Test", "email": email})
        assert response.status_code == 200
        assert f'action="{PAY_URL}"'.encode() in response.data
        destination = urlsplit(PAY_URL)
        origin = f"{destination.scheme}://{destination.netloc}"
        directives = response.headers["Content-Security-Policy"].split("; ")
        assert f"form-action 'self' {origin}" in directives
        for path in ("/products/", "/admin/login/"):
            policy = client.get(path).headers["Content-Security-Policy"].split("; ")
            assert "form-action 'self'" in policy
            assert origin not in "; ".join(policy)
        invalid = client.post(f"/products/{slug}/checkout/", data={"email": "invalid"})
        assert "form-action 'self'" in invalid.headers["Content-Security-Policy"].split("; ")
    finally:
        with app.app_context():
            Order.query.filter_by(email=email).delete()
            db.session.commit()


def test_paid_order_missing_from_catalog_can_be_refunded(client, monkeypatch):
    import app as app_module
    from decimal import Decimal
    from extensions import db
    from models import AdminUser, Order

    app = app_module.app
    email = "refund-catalog-test@example.com"
    calls = []

    def fake_refund(order, product, config, amount):
        calls.append((order.id, product, amount))
        return {"op_key": "operation-key", "request_id": "refund-request"}

    monkeypatch.setattr(app_module, "create_refund", fake_refund)
    with app.app_context():
        admin_id = str(AdminUser.query.first().id)
        order = Order(product_slug="removed-service", product_name="Recorded service",
                      amount=Decimal("10.00"), email=email, status="paid")
        db.session.add(order)
        db.session.commit()
        order_id = order.id
    try:
        with client.session_transaction() as session:
            session["_user_id"] = admin_id
            session["_fresh"] = True
        response = client.post(f"/admin/orders/{order_id}/refund/", data={})
        assert response.status_code == 302
        assert len(calls) == 1
        assert calls[0][1]["name"] == "Recorded service"
        assert calls[0][1]["price"] == Decimal("10.00")
        assert calls[0][1]["payment_object"] == "service"
        assert calls[0][2] is None
        with app.app_context():
            order = db.session.get(Order, order_id)
            assert order.status == "refund_processing"
            assert order.refund_request_id == "refund-request"
            assert order.refund_amount == Decimal("10.00")
        # A repeated click must not submit another refund.
        client.post(f"/admin/orders/{order_id}/refund/", data={})
        assert len(calls) == 1
    finally:
        with app.app_context():
            Order.query.filter_by(email=email).delete()
            db.session.commit()
