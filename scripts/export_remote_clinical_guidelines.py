"""Read official metadata on the portal VPS; return JSON without changing its DB.

GitHub Actions sends this file to `docker compose exec -T app python -` over SSH.
Only a temporary registry/vault is written; the portal registry and user notes
are never changed by this export. GitHub merges successful sources separately.
"""
import argparse
import json
import tempfile
from pathlib import Path

import requests

from scripts import sync_clinical_guidelines_vault as collector


def export_snapshot(pages=5, full=False):
    with tempfile.TemporaryDirectory(prefix="medical-source-export-") as temporary:
        root = Path(temporary)
        original_registry, original_vault = collector.REGISTRY_PATH, collector.VAULT_DIR
        original_fetch = collector.fetch_minzdrav_page
        try:
            collector.REGISTRY_PATH = root / "registry.json"
            collector.VAULT_DIR = root / "vault"
            # requests.post открывает отдельное TCP/TLS-соединение для каждой
            # страницы. На нестабильном API первая страница проходила, а новое
            # соединение второй истекало. Одна Session сохраняет keep-alive.
            with requests.Session() as session:
                def fetch_page(**kwargs):
                    return original_fetch(**kwargs, request_post=session.post)
                collector.fetch_minzdrav_page = fetch_page
                result = collector.sync(pages, full)
            items = json.loads(collector.REGISTRY_PATH.read_text())["items"]
        finally:
            collector.REGISTRY_PATH, collector.VAULT_DIR = original_registry, original_vault
            collector.fetch_minzdrav_page = original_fetch
    return {"schema_version": 1, "result": result, "items": items, "collection_location": "portal-vps"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pages", type=int, default=5)
    parser.add_argument("--full", action="store_true")
    args = parser.parse_args()
    print(json.dumps(export_snapshot(max(1, args.pages), args.full), ensure_ascii=False))
