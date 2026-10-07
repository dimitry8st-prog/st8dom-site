import hashlib
from types import SimpleNamespace

import pytest

from payments_robokassa import enabled, payment_form, valid_result_signature, valid_success_signature


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
