"""Read-only Life-OS inventory for the Vitalis boundary audit.

Run from the portal repository root:
    python -m scripts.export_vitalis_lifeos --output /private/path/lifeos-vitalis.json

The command never changes the portal database. Portal articles and raw Life-OS notes are
never RAG sources for Vitalis. ``approved_records`` therefore stays empty; only verified
full clinical guidelines may be indexed through the separate guideline pipeline. Raw
Life-OS materials remain inventory candidates without their body or a review decision.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = 2


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
    portal_article_count = sum(1 for _ in articles)

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
        "eligibility_policy": "verified_full_clinical_guidelines_only",
        "approved_records": [],
        "portal_articles_excluded": portal_article_count,
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
                "portal_articles_excluded": payload["portal_articles_excluded"],
                "candidates": len(payload["candidates"]),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
