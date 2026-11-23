from news_sources import NEWS_SOURCES, source_by_key, sources_for


def test_registry_keys_and_urls_are_unique():
    keys = [source.key for source in NEWS_SOURCES]
    urls = [source.url for source in NEWS_SOURCES]
    assert len(keys) == len(set(keys))
    assert len(urls) == len(set(urls))


def test_enabled_sources_have_supported_adapters():
    enabled = sources_for(enabled=True)
    assert enabled
    assert {source.adapter for source in enabled} <= {
        "securitylab_rss",
        "mit_rss",
        "mcp_rss",
        "openai_html",
    }


def test_official_ai_coverage_gaps_are_explicit():
    expected = {"anthropic-news", "google-ai"}
    registered = {source.key for source in NEWS_SOURCES}
    assert expected <= registered
    for key in expected:
        source = source_by_key(key)
        assert source.enabled is False
        assert source.status == "adapter_required"


def test_mit_is_required_and_resolved_by_key():
    source = source_by_key("mit-news")
    assert source.required is True
    assert source.adapter == "mit_rss"


def test_openai_adapter_is_enabled_for_private_cards():
    source = source_by_key("openai-news")
    assert source.enabled is True
    assert source.adapter == "openai_html"
    assert source.stream == "science-ai"


def test_mcp_adapter_is_enabled_for_private_cards():
    source = source_by_key("mcp-blog")
    assert source.enabled is True
    assert source.adapter == "mcp_rss"
    assert source.stream == "science-ai"
