"""Проверяем навигацию и безопасность публичного каталога промптов."""

import json

from prompt_library import CATEGORIES, all_prompts


def test_prompt_categories_search_and_details(client):
    catalog = all_prompts()
    assert len(catalog) == 37
    page = client.get("/directions/ai/prompts/")
    assert page.status_code == 200
    for slug, name in CATEGORIES:
        assert name.encode() in page.data
        category_page = client.get(f"/directions/ai/prompts/?category={slug}")
        assert category_page.status_code == 200
        assert category_page.data.count(b'class="prompt-card"') == sum(
            item["category"] == slug for item in catalog
        )

    results = client.get("/directions/ai/prompts/?q=резюме")
    assert "Достижения в резюме".encode() in results.data
    detail = client.get("/directions/ai/prompts/work/resume-achievements/")
    assert detail.status_code == 200
    assert "Не добавляй выдуманные навыки".encode() in detail.data
    assert b'id="copy-prompt"' in detail.data
    assert client.get("/directions/ai/prompts/work/unknown/").status_code == 404
    assert client.get("/directions/ai/prompts/unknown/resume-achievements/").status_code == 404


def test_prompts_in_sitemap_and_escaped(client):
    sitemap = client.get("/sitemap.xml")
    assert b"/directions/ai/prompts/content/city-weather/" in sitemap.data
    page = client.get("/directions/ai/prompts/verification/answer-with-sources/")
    assert b"&lt;" not in page.data  # The curated template is plain text.
    assert b"<pre class=\"prompt-text\"" in page.data


def test_copyable_cocktail_templates_are_valid_json():
    templates = {item["slug"]: item for item in all_prompts()}
    for slug in ("cocktail-card", "cocktail-presentation"):
        recipe = json.loads(templates[slug]["body"])
        assert recipe["cocktail"]["ingredients"]
        assert recipe["render"]["composition"]
