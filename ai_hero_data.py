"""Exact AI hero image embedded as base64 chunks."""

import base64

PARTS: list[str] = []


def image_bytes() -> bytes:
    return base64.b64decode("".join(PARTS))
