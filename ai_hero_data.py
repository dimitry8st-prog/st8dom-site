"""Embedded AI hero image assembled from base64 text chunks."""

import base64

PARTS: list[str] = []


def image_bytes() -> bytes:
    return base64.b64decode("".join(PARTS))
