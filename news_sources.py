"""Managed registry of portal news sources.

Only enabled sources are collected automatically. Catalog entries with
adapter_required make coverage gaps explicit without pretending that an HTML
page is a stable RSS or API endpoint.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NewsSource:
    key: str
    provider: str
    url: str
    stream: str
    adapter: str
    required: bool = False
    enabled: bool = True
    fallback_url: str | None = None
    unavailable_statuses: tuple[int, ...] = (404, 410)
    status: str = "active"


NEWS_SOURCES: tuple[NewsSource, ...] = (
    NewsSource(
        key="news",
        provider="SecurityLab",
        url="https://www.securitylab.ru/_Services/Export/RSS/news/",
        stream="security",
        adapter="securitylab_rss",
        required=True,
    ),
    NewsSource(
        key="vulnerabilities",
        provider="SecurityLab",
        url="https://www.securitylab.ru/_Services/Export/RSS/vulnerabilities/",
        stream="security",
        adapter="securitylab_rss",
        fallback_url="https://www.securitylab.ru/_Services/Export/RSS/",
    ),
    NewsSource(
        key="analytics",
        provider="SecurityLab",
        url="https://www.securitylab.ru/_Services/Export/RSS/analytics/",
        stream="security",
        adapter="securitylab_rss",
    ),
    NewsSource(
        key="software",
        provider="SecurityLab",
        url="https://www.securitylab.ru/_Services/Export/RSS/software/",
        stream="security",
        adapter="securitylab_rss",
        status="optional",
    ),
    NewsSource(
        key="mit-news",
        provider="MIT News",
        url="https://news.mit.edu/rss/feed",
        stream="science",
        adapter="mit_rss",
        required=True,
    ),
    NewsSource(
        key="openai-news",
        provider="OpenAI",
        url="https://openai.com/news/product-releases/",
        stream="science-ai",
        adapter="html",
        enabled=False,
        status="adapter_required",
    ),
    NewsSource(
        key="anthropic-news",
        provider="Anthropic",
        url="https://www.anthropic.com/news",
        stream="science-ai",
        adapter="html",
        enabled=False,
        status="adapter_required",
    ),
    NewsSource(
        key="google-ai",
        provider="Google",
        url="https://blog.google/innovation-and-ai/technology/ai/",
        stream="science-ai",
        adapter="html",
        enabled=False,
        status="adapter_required",
    ),
    NewsSource(
        key="mcp-blog",
        provider="Model Context Protocol",
        url="https://blog.modelcontextprotocol.io/",
        stream="science-ai",
        adapter="html",
        enabled=False,
        status="adapter_required",
    ),
    NewsSource(
        key="aaif",
        provider="Agentic AI Foundation",
        url="https://aaif.io/blog",
        stream="science-ai",
        adapter="aaif_weekly",
        enabled=False,
        status="separate_workflow",
    ),
)


def sources_for(*, provider: str | None = None, adapter: str | None = None,
                enabled: bool | None = None) -> tuple[NewsSource, ...]:
    result = NEWS_SOURCES
    if provider is not None:
        result = tuple(source for source in result if source.provider == provider)
    if adapter is not None:
        result = tuple(source for source in result if source.adapter == adapter)
    if enabled is not None:
        result = tuple(source for source in result if source.enabled is enabled)
    return result


def source_by_key(key: str) -> NewsSource:
    matches = tuple(source for source in NEWS_SOURCES if source.key == key)
    if len(matches) != 1:
        raise KeyError(f"News source is missing or duplicated: {key}")
    return matches[0]
