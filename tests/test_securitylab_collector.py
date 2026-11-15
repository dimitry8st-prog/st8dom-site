"""Unavailable RSS fallback, deduplication, and genuine collection failures."""
import pytest
import requests

import lifeos_workspace as workspace
from scripts import collect_portal_news as collector


RSS = b'''<rss><channel><item><title>Security update</title>
<link>https://www.securitylab.ru/news/collector-test.php</link>
</item></channel></rss>'''
EMPTY_RSS = b"<rss><channel/></rss>"


def response(url, status=200, body=RSS):
    result = requests.Response()
    result.status_code = status
    result.url = url
    result._content = body
    result._content_consumed = True
    return result


def setup_source(monkeypatch, status, fallback_status=200, fallback_body=RSS):
    monkeypatch.setattr(workspace.time, "sleep", lambda delay: None)
    primary = workspace.FEEDS["vulnerabilities"]
    fallback = workspace.FEED_FALLBACKS["vulnerabilities"]
    news = workspace.FEEDS["news"]
    monkeypatch.setattr(workspace, "FEEDS", {"vulnerabilities": primary, "news": news})
    calls, saved = [], set()

    def get(url, **kwargs):
        calls.append(url)
        if url == primary:
            return response(url, status)
        if url == fallback:
            return response(url, fallback_status, fallback_body)
        assert url == news
        return response(url)

    def save(stream, **fields):
        assert stream == "security"
        url = fields["source_url"]
        added = url not in saved
        saved.add(url)
        return None, added

    monkeypatch.setattr(workspace.requests, "get", get)
    monkeypatch.setattr(workspace, "save_material", save)
    return primary, fallback, news, calls


@pytest.mark.parametrize("status", [404, 410])
def test_removed_feed_uses_main_rss_with_warning_and_no_duplicates(monkeypatch, status):
    primary, fallback, news, calls = setup_source(monkeypatch, status)
    warnings = []
    assert workspace.collect_securitylab(warnings=warnings) == (1, [])
    assert calls == [primary, fallback, news]
    assert len(warnings) == 1
    assert f"HTTP {status}" in warnings[0]
    assert "specialized vulnerability-feed coverage is unavailable" in warnings[0]
    assert workspace.collect_securitylab() == (0, [])


@pytest.mark.parametrize("status", [403, 429, 500])
def test_access_and_server_failures_stay_errors_and_other_feeds_continue(monkeypatch, status):
    primary, _, news, calls = setup_source(monkeypatch, status)
    warnings = []
    assert workspace.collect_securitylab(warnings=warnings) == (1, [f"vulnerabilities: HTTP {status}"])
    assert calls == [primary] * (3 if status == 500 else 1) + [news]
    assert warnings == []


@pytest.mark.parametrize("status,body,error", [
    (503, EMPTY_RSS, "HTTP 503"),
    (200, b"<html>not RSS</html>", "ValueError"),
    (200, b"x" * (4 * 1024 * 1024 + 1), "ValueError"),
])
def test_bad_fallback_is_fatal_and_never_reports_recovery(monkeypatch, status, body, error):
    setup_source(monkeypatch, 404, status, body)
    warnings = []
    assert workspace.collect_securitylab(warnings=warnings) == (1, [f"vulnerabilities: {error}"])
    assert warnings == []


def test_restored_specialized_feed_stops_using_fallback(monkeypatch):
    primary, _, news, calls = setup_source(monkeypatch, 200)
    warnings = []
    assert workspace.collect_securitylab(warnings=warnings) == (1, [])
    assert calls == [primary, news]
    assert warnings == []


def test_feed_redirect_outside_source_is_rejected(monkeypatch):
    monkeypatch.setattr(workspace.requests, "get", lambda *a, **kw: response("https://example.org/rss"))
    with pytest.raises(ValueError, match="outside official source"):
        workspace._fetch_securitylab_feed(workspace.FEEDS["news"])


@pytest.mark.parametrize("first_error", [requests.ReadTimeout("test"), requests.ConnectionError("test"), 503])
def test_transient_source_failure_recovers_before_saving(monkeypatch, first_error):
    url = workspace.FEEDS["analytics"]
    calls = []
    monkeypatch.setattr(workspace.time, "sleep", lambda delay: None)

    def get(*args, **kwargs):
        calls.append(args[0])
        if len(calls) == 1:
            if isinstance(first_error, Exception):
                raise first_error
            return response(url, first_error)
        return response(url)

    monkeypatch.setattr(workspace.requests, "get", get)
    rows = workspace._fetch_securitylab_feed(url)
    assert len(rows) == 1
    assert calls == [url, url]


def test_command_exposes_fallback_warning_and_preserves_mit_failure(monkeypatch, capsys):
    def collect(*, warnings):
        warnings.append("vulnerabilities: HTTP 404; main RSS used")
        return 0, []

    monkeypatch.setattr(collector, "collect_securitylab", collect)
    monkeypatch.setattr(collector, "collect_mit", lambda: {"matched": 0, "created": 0, "existing": 0})
    collector.main()
    assert "::warning title=SecurityLab RSS::vulnerabilities: HTTP 404" in capsys.readouterr().out

    def fail_mit():
        raise requests.Timeout("test")

    monkeypatch.setattr(collector, "collect_mit", fail_mit)
    with pytest.raises(SystemExit, match="News collection incomplete: MIT: Timeout"):
        collector.main()
