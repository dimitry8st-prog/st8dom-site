import pytest
from scripts.collect_portal_news import parse_mit_feed


def test_mit_filter_and_untrusted_links():
    rows = parse_mit_feed(b'''<rss><channel>
      <item><title>Brain engineering</title><link>https://news.mit.edu/2026/brain</link><description>Medical research</description><pubDate>Fri, 30 Oct 2026</pubDate></item>
      <item><title>AI duplicate</title><link>https://news.mit.edu/2026/brain</link></item>
      <item><title>AI external</title><link>https://example.org/x</link></item>
      <item><title>Campus meal</title><link>https://news.mit.edu/2026/meal</link></item>
    </channel></rss>''')
    assert len(rows) == 1
    assert rows[0]['stream'] == 'science-neuro'
    assert rows[0]['published_date'] == 'Fri, 30 Oct 2026'


def test_mit_rejects_html_and_oversize():
    for data in [b'<html>blocked</html>', b'x' * (4 * 1024 * 1024 + 1)]:
        with pytest.raises(ValueError):
            parse_mit_feed(data)
