"""Scoped n8n bridge: save an invoice, then explicitly enqueue its first email.

No model, SMTP or payment API is called inside these handlers. Bearer access
never grants admin access, arbitrary prices, paid status, refunds or old orders.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

from email_validator import EmailNotValidError, validate_email
from flask import Blueprint, current_app, g, jsonify, request
from sqlalchemy.exc import IntegrityError

from assistant.rate_limit import SlidingWindowLimiter
from extensions import csrf, db
from models import Order, OrderCheckout, OrderNotification
from order_automation import (
    CheckoutConflict, INITIAL_PAYMENT_STATES, create_checkout, payment_link,
    saved_product,
)
from payments_robokassa import enabled as payment_enabled
from products import PRODUCTS_BY_SLUG

ALLOWED_PRODUCTS = frozenset({"express-review", "ai-audit"})
REQUEST_ID = re.compile(r"[A-Za-z0-9_-]{16,128}\Z", re.ASCII)
AMOUNT = re.compile(r"[0-9]{1,10}(?:\.[0-9]{1,6})?\Z", re.ASCII)
INPUT_FIELDS = frozenset({
    "request_id", "product_slug", "amount", "name", "email", "contact", "comment", "analysis",
})
ANALYSIS_LIMITS = {
    "client_name": 120, "request_type": 80, "request_summary": 1200,
    "payment_description": 220, "amount": 20, "priority": 10,
}
MAX_BODY_BYTES = 24_000


def request_key(request_id):
    return hashlib.sha256(("n8n-orders-v1:" + request_id).encode("ascii")).hexdigest()


def _text(value, maximum, *, required=False):
    if not isinstance(value, str):
        raise ValueError("invalid_text")
    value = value.strip()
    if len(value) > maximum or (required and not value):
        raise ValueError("invalid_text")
    if any(ord(character) < 32 and character not in "\n\r\t" for character in value):
        raise ValueError("invalid_text")
    return value


def _amount(value):
    if not isinstance(value, str) or not AMOUNT.fullmatch(value):
        raise ValueError("invalid_amount")
    try:
        amount = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("invalid_amount") from exc
    if not amount.is_finite() or amount <= 0:
        raise ValueError("invalid_amount")
    return amount


def _lookup(request_id):
    if not isinstance(request_id, str) or not REQUEST_ID.fullmatch(request_id):
        raise ValueError("invalid_request_id")
    snapshot = OrderCheckout.query.filter_by(request_key=request_key(request_id)).first()
    order = db.session.get(Order, snapshot.order_id) if snapshot else None
    return order, snapshot


def _mode_matches(snapshot):
    return snapshot.test_mode == bool(current_app.config.get("ROBOKASSA_TEST_MODE"))


def _response(order, snapshot, request_id):
    notice = OrderNotification.query.filter_by(order_id=order.id, kind="payment_link").first()
    return jsonify({
        "request_id": request_id, "order_id": order.id,
        "product_slug": order.product_slug, "product_name": order.product_name,
        "amount": f"{order.amount:.2f}", "status": order.status,
        "payment_link": payment_link(snapshot, current_app.config),
        "notification_status": notice.status if notice else "not_queued",
    })


def make_orders_blueprint():
    api = Blueprint("api_n8n_orders", __name__, url_prefix="/api/automation/orders")
    # These routes use explicit bearer authorization, never browser cookie auth.
    csrf.exempt(api)
    limiter = SlidingWindowLimiter(max_hits=60, window_sec=300)

    @api.before_request
    def authorize():
        expected = current_app.config.get("N8N_ORDERS_API_TOKEN") or ""
        if not expected:
            return jsonify({"error": "not_found"}), 404
        if len(expected) < 32:
            return jsonify({"error": "api_not_configured"}), 503
        authorization = request.headers.get("Authorization", "")
        supplied = authorization[7:] if authorization.startswith("Bearer ") else ""
        if not hmac.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8")):
            return jsonify({"error": "unauthorized"}), 401
        # Unauthenticated probes must not consume the legitimate caller's quota.
        # A single bounded per-worker bucket also avoids caller-key memory growth.
        if not limiter.allow("n8n-order-api"):
            return jsonify({"error": "rate_limited"}), 429
        if request.content_length and request.content_length > MAX_BODY_BYTES:
            return jsonify({"error": "body_too_large"}), 413
        if request.method == "POST":
            # Bounded stream read also covers chunked bodies. It works on the
            # supported Flask 3.0 baseline (per-request size setters need 3.1).
            g.n8n_order_body = request.stream.read(MAX_BODY_BYTES + 1)
            if len(g.n8n_order_body) > MAX_BODY_BYTES:
                return jsonify({"error": "body_too_large"}), 413
            try:
                g.n8n_order_payload = json.loads(g.n8n_order_body) if request.is_json else None
            except (json.JSONDecodeError, UnicodeDecodeError):
                g.n8n_order_payload = None
        try:
            origin = urlsplit(current_app.config.get("SITE_URL") or "")
        except ValueError:
            return jsonify({"error": "payment_configuration_invalid"}), 503
        if (origin.scheme != "https" or not origin.netloc or origin.username or origin.password
                or origin.query or origin.fragment):
            return jsonify({"error": "payment_configuration_invalid"}), 503

    @api.after_request
    def private_response(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
        return response

    @api.post("/")
    def create_order():
        payload = g.n8n_order_payload
        if not isinstance(payload, dict) or set(payload) != INPUT_FIELDS:
            return jsonify({"error": "invalid_fields"}), 400
        try:
            request_id = payload["request_id"]
            order, snapshot = _lookup(request_id)
            slug = payload["product_slug"]
            if not isinstance(slug, str) or slug not in ALLOWED_PRODUCTS:
                raise ValueError("invalid_product")
            product = PRODUCTS_BY_SLUG.get(slug)
            if not product or not product.get("sellable") or not product.get("price"):
                raise ValueError("invalid_product")
            if order:
                if not _mode_matches(snapshot):
                    return jsonify({"error": "payment_mode_changed"}), 409
                if order.product_slug != slug:
                    raise CheckoutConflict("request_conflict")
                expected_amount = Decimal(order.amount)
                product = {**saved_product(order, snapshot), "slug": slug}
            else:
                expected_amount = Decimal(str(product["price"]))
            if _amount(payload["amount"]) != expected_amount:
                raise ValueError("catalog_amount_mismatch")
            email = _text(payload["email"], 255, required=True)
            email = validate_email(email, check_deliverability=False).normalized.lower()
            name = _text(payload["name"], 120)
            contact = _text(payload["contact"], 120)
            comment = _text(payload["comment"], 3000)
            analysis = payload["analysis"]
            if not isinstance(analysis, dict) or set(analysis) != set(ANALYSIS_LIMITS):
                raise ValueError("invalid_analysis")
            analysis = {key: _text(analysis[key], maximum, required=True)
                        for key, maximum in ANALYSIS_LIMITS.items()}
            if analysis["priority"] not in {"normal", "high", "low"}:
                raise ValueError("invalid_priority")
            if _amount(analysis["amount"]) != expected_amount:
                raise ValueError("analysis_amount_mismatch")
            analysis["amount"] = f"{expected_amount:.2f}"
            # Descriptive AI output is stored as data. It cannot set price,
            # payment state, sender, destination or payment-system parameters.
            stored_comment = json.dumps({"comment": comment, "analysis": analysis},
                                        ensure_ascii=False, sort_keys=True)
            if not payment_enabled(current_app.config):
                return jsonify({"error": "payments_unavailable"}), 503
            order, snapshot = create_checkout(product, {
                "email": email, "name": name, "contact": contact, "comment": stored_comment,
            }, current_app.config, request_key(request_id), queue_notification=False)
        except CheckoutConflict:
            return jsonify({"error": "request_conflict"}), 409
        except (ValueError, EmailNotValidError):
            return jsonify({"error": "invalid_request"}), 400
        return _response(order, snapshot, request_id)

    @api.get("/<request_id>/")
    def get_order(request_id):
        try:
            order, snapshot = _lookup(request_id)
        except ValueError:
            return jsonify({"error": "invalid_request_id"}), 400
        if order is None:
            return jsonify({"error": "not_found"}), 404
        if not _mode_matches(snapshot):
            return jsonify({"error": "payment_mode_changed"}), 409
        return _response(order, snapshot, request_id)

    @api.post("/<request_id>/notify/")
    def notify_order(request_id):
        payload = g.n8n_order_payload
        if g.n8n_order_body and payload != {}:
            return jsonify({"error": "invalid_fields"}), 400
        try:
            order, snapshot = _lookup(request_id)
        except ValueError:
            return jsonify({"error": "invalid_request_id"}), 400
        if order is None:
            return jsonify({"error": "not_found"}), 404
        if not _mode_matches(snapshot):
            return jsonify({"error": "payment_mode_changed"}), 409
        if order.status not in INITIAL_PAYMENT_STATES:
            return jsonify({"error": "order_already_closed"}), 409
        notice = OrderNotification.query.filter_by(order_id=order.id, kind="payment_link").first()
        if notice is None:
            db.session.add(OrderNotification(order_id=order.id, kind="payment_link"))
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                # A concurrent notify is accepted only if it created this notice.
                if not OrderNotification.query.filter_by(order_id=order.id, kind="payment_link").first():
                    raise
        return _response(order, snapshot, request_id)

    return api
