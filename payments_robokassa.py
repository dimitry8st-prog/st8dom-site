"""Robokassa: создание платежей, проверка уведомлений и возвраты."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from urllib.parse import quote
from xml.etree import ElementTree

import jwt
import requests


PAY_URL = "https://auth.robokassa.ru/Merchant/Index.aspx"
OPSTATE_URL = "https://auth.robokassa.ru/Merchant/WebService/Service.asmx/OpStateExt"
REFUND_URL = "https://services.robokassa.ru/RefundService/Refund/Create"
REFUND_STATE_URL = "https://services.robokassa.ru/RefundService/Refund/GetState"


def money(value) -> str:
    return f"{Decimal(str(value)):.2f}"


def enabled(config) -> bool:
    prefix = "ROBOKASSA_TEST_PASSWORD" if config.get("ROBOKASSA_TEST_MODE") else "ROBOKASSA_PASSWORD"
    return bool(
        config.get("ROBOKASSA_MERCHANT_LOGIN")
        and config.get(prefix + "1")
        and config.get(prefix + "2")
    )


def build_receipt(product: dict) -> tuple[str, str]:
    payload = {
        "items": [
            {
                "name": product["name"][:128],
                "quantity": 1,
                "sum": float(product["price"]),
                "tax": "none",
                "payment_method": "full_payment",
                "payment_object": product.get("payment_object", "service"),
            }
        ]
    }
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return raw, quote(raw, safe="")


def payment_form(order, product: dict, config) -> dict:
    merchant = config["ROBOKASSA_MERCHANT_LOGIN"]
    password1 = (
        config.get("ROBOKASSA_TEST_PASSWORD1")
        if config.get("ROBOKASSA_TEST_MODE")
        else config.get("ROBOKASSA_PASSWORD1")
    )
    if not password1:
        raise ValueError("Не задан пароль №1 для выбранного режима Robokassa.")
    amount = money(order.amount)
    _receipt_raw, receipt_encoded = build_receipt(product)
    signature = hashlib.md5(
        f"{merchant}:{amount}:{order.id}:{receipt_encoded}:{password1}".encode("utf-8")
    ).hexdigest()
    fields = {
        "MerchantLogin": merchant,
        "OutSum": amount,
        "InvId": str(order.id),
        "Description": product["name"][:100],
        "SignatureValue": signature,
        "Email": order.email,
        "Culture": "ru",
        "Receipt": receipt_encoded,
    }
    if config.get("ROBOKASSA_TEST_MODE"):
        fields["IsTest"] = "1"
    return {"url": PAY_URL, "fields": fields}


def valid_result_signature(out_sum: str, inv_id: str, signature: str, config) -> bool:
    password2 = (
        config.get("ROBOKASSA_TEST_PASSWORD2")
        if config.get("ROBOKASSA_TEST_MODE")
        else config.get("ROBOKASSA_PASSWORD2")
    )
    if not password2:
        return False
    expected = hashlib.md5(
        f"{out_sum}:{inv_id}:{password2}".encode("utf-8")
    ).hexdigest()
    return expected.casefold() == (signature or "").casefold()


def valid_success_signature(out_sum: str, inv_id: str, signature: str, config) -> bool:
    password1 = (
        config.get("ROBOKASSA_TEST_PASSWORD1")
        if config.get("ROBOKASSA_TEST_MODE")
        else config.get("ROBOKASSA_PASSWORD1")
    )
    if not password1:
        return False
    expected = hashlib.md5(
        f"{out_sum}:{inv_id}:{password1}".encode("utf-8")
    ).hexdigest()
    return expected.casefold() == (signature or "").casefold()


def fetch_op_key(order, config) -> str | None:
    if config.get("ROBOKASSA_TEST_MODE"):
        return None
    signature = hashlib.md5(
        f"{config['ROBOKASSA_MERCHANT_LOGIN']}:{order.id}:{config['ROBOKASSA_PASSWORD2']}".encode("utf-8")
    ).hexdigest()
    response = requests.get(
        OPSTATE_URL,
        params={
            "MerchantLogin": config["ROBOKASSA_MERCHANT_LOGIN"],
            "InvoiceID": order.id,
            "Signature": signature,
        },
        timeout=15,
    )
    response.raise_for_status()
    root = ElementTree.fromstring(response.text)
    for node in root.iter():
        if node.tag.endswith("OpKey") and node.text:
            return node.text.strip()
    return None


def create_refund(order, product: dict, config, amount: Decimal | None = None) -> dict:
    password3 = config.get("ROBOKASSA_PASSWORD3")
    if not password3:
        raise RuntimeError("В Robokassa не задан Password3 для возвратов.")
    op_key = order.robokassa_op_key or fetch_op_key(order, config)
    if not op_key:
        raise RuntimeError("Не удалось получить OpKey операции Robokassa.")

    item_cost = float(amount if amount is not None else order.amount)
    payload = {
        "OpKey": op_key,
        "InvoiceItems": [
            {
                "Name": product["name"][:128],
                "Quantity": 1,
                "Cost": item_cost,
                "Tax": "none",
                "PaymentMethod": "full_payment",
                "PaymentObject": product.get("payment_object", "service"),
            }
        ],
    }
    if amount is not None and Decimal(str(amount)) < Decimal(str(order.amount)):
        payload["RefundSum"] = float(amount)

    token = jwt.encode(payload, password3, algorithm="HS256")
    response = requests.post(REFUND_URL, json=token, timeout=20)
    response.raise_for_status()
    data = response.json()
    if not data.get("success"):
        raise RuntimeError(data.get("message") or "Robokassa отклонила возврат.")
    return {"request_id": data.get("requestId"), "op_key": op_key}


def refund_state(request_id: str) -> dict:
    response = requests.get(REFUND_STATE_URL, params={"id": request_id}, timeout=15)
    response.raise_for_status()
    return response.json()
