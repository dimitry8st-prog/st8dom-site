"""Read-only Life-OS export for the Vitalis offline review pipeline.

Run from the portal repository root:
    python -m scripts.export_vitalis_lifeos --output /private/path/lifeos-vitalis.json

The command never changes the portal database. Only published medical articles with a
recorded medical reviewer and review date enter ``approved_records``. Raw Life-OS
materials are listed as candidates without their body and are never approved implicitly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = 1
NEURO_RUBRIC_PREFIX = "neurology-neurosurgery-"


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def build_export(
    articles: Iterable[Any],
    lifeos_candidates: Iterable[Any],
    *,
    site_url: str,
) -> dict[str, Any]:
    approved_records: list[dict[str, Any]] = []
    for article in articles:
        rubric_slug = str(getattr(getattr(article, "rubric", None), "slug", ""))
        if (
            getattr(article, "section", None) != "medicine"
            or getattr(article, "status", None) != "published"
            or getattr(article, "published_at", None) is None
            or not str(getattr(article, "medical_reviewer", "") or "").strip()
            or getattr(article, "reviewed_at", None) is None
            or not rubric_slug.startswith(NEURO_RUBRIC_PREFIX)
        ):
            continue
        body = str(getattr(article, "body", "") or "").strip()
        sources = [
            {
                "title": str(getattr(source, "title", "") or "").strip(),
                "url": str(getattr(source, "url", "") or "").strip(),
                "accessed_at": _iso(getattr(source, "accessed_at", None)),
            }
            for source in getattr(article, "sources", [])
            if str(getattr(source, "url", "") or "").startswith("https://")
        ]
        if len(body) < 100 or not sources:
            continue
        slug = str(getattr(article, "slug", "") or "").strip()
        approved_records.append(
            {
                "source_id": f"portal-article-{slug}",
                "title": str(getattr(article, "title", "") or "").strip(),
                "summary": str(getattr(article, "summary", "") or "").strip(),
                "body": body,
                "body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
                "portal_url": f"{site_url.rstrip('/')}/materials/{slug}/",
                "source_version": _iso(getattr(article, "updated_at", None)),
                "published_at": _iso(getattr(article, "published_at", None)),
                "reviewed_at": _iso(getattr(article, "reviewed_at", None)),
                "reviewed_by": str(
                    getattr(article, "medical_reviewer", "") or ""
                ).strip(),
                "author": str(getattr(article, "author", "") or "").strip(),
                "rubric": rubric_slug,
                "specialty_tags": ["neurology", "neurosurgery"],
                "tags": sorted(
                    str(getattr(tag, "name", "") or "").strip()
                    for tag in getattr(article, "tags", [])
                    if str(getattr(tag, "name", "") or "").strip()
                ),
                "content_scope": "reviewed_excerpt",
                "review_status": "approved",
                "sources": sources,
            }
        )

    candidates = [
        {
            "source_id": f"lifeos-material-{item.id}",
            "title": str(item.title or "").strip(),
            "source_url": str(item.source_url or "").strip(),
            "stream": str(item.stream or ""),
            "evidence": str(item.evidence or ""),
            "created_at": _iso(item.created_at),
            "body_sha256": hashlib.sha256(
                str(item.body or "").encode("utf-8")
            ).hexdigest(),
            "review_status": "needs_medical_review",
        }
        for item in lifeos_candidates
        if str(getattr(item, "stream", "")) == "science-neuro"
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "source_system": "st8dom-lifeos",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "automatic_ingestion": False,
        "approved_records": sorted(
            approved_records, key=lambda record: record["source_id"]
        ),
        "candidates": sorted(candidates, key=lambda record: record["source_id"]),
    }


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only export of reviewed portal Life-OS material for Vitalis"
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    from app import app
    from models import Article, LifeOSMaterial

    with app.app_context():
        articles = Article.query.order_by(Article.slug).all()
        candidates = LifeOSMaterial.query.filter_by(stream="science-neuro").order_by(
            LifeOSMaterial.id
        ).all()
        payload = build_export(
            articles,
            candidates,
            site_url=str(app.config["SITE_URL"]),
        )
    _atomic_json(args.output, payload)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "approved": len(payload["approved_records"]),
                "candidates": len(payload["candidates"]),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
