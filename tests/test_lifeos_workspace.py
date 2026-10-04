import base64
import pytest
from app import app
from extensions import db
from models import LifeOSMaterial, AdminUser
from lifeos_workspace import parse_feed, save_material


def login(client):
    with app.app_context():
        user_id = str(AdminUser.query.first().id)
    with client.session_transaction() as session:
        session['_user_id'] = user_id
        session['_fresh'] = True


def test_workspace_requires_auth_and_preserves_blocks(client):
    assert client.get('/directions/life-os/dis/security/').status_code == 401
    login(client)
    page = client.get('/directions/life-os/')
    assert 'ДИС — рабочая система'.encode() in page.data
    for stream in ('time', 'culture', 'security'):
        assert f'/directions/life-os/dis/{stream}/'.encode() in page.data
        assert client.get(f'/directions/life-os/dis/{stream}/').status_code == 200
    assert client.get('/directions/life-os/dis/unknown/').status_code == 404


def test_reader_cannot_write(client):
    password = app.config['LIFEOS_PASSWORD']
    auth = base64.b64encode(f"{app.config['LIFEOS_USERNAME']}:{password}".encode()).decode()
    result = client.post('/directions/life-os/dis/time/', headers={'Authorization': 'Basic ' + auth}, data={'title':'x','source_url':'https://example.org'})
    assert result.status_code == 403


def test_storage_dedup_search_and_summary_only(client):
    login(client)
    with app.app_context():
        try:
            first, created = save_material('security','CVE-2099-1234 проверка','https://www.securitylab.ru/news/test-dis.php?utm_source=test',body='<script>alert(1)</script> полный материал',summary='Короткий отчёт')
            assert created
            second, created = save_material('security','дубль','https://www.securitylab.ru/news/test-dis.php#anchor')
            assert not created and second.id == first.id
            assert client.get('/directions/life-os/dis/culture/?q=CVE-2099-1234').data.count(b'CVE-2099-1234') == 1  # only the search field
            page = client.get('/directions/life-os/dis/security/?q=CVE-2099-1234')
            assert 'Короткий отчёт'.encode() in page.data
            detail = client.get(f'/directions/life-os/dis/material/{first.id}/')
            assert b'<script>alert(1)</script>' not in detail.data
            report = client.get(f'/directions/life-os/dis/notion-report/{first.id}/').json
            assert set(report) == {'title','report','portal_url'}
            assert 'полный материал' not in str(report)
        finally:
            LifeOSMaterial.query.filter_by(source_url='https://www.securitylab.ru/news/test-dis.php').delete()
            db.session.commit()


def test_feed_validation():
    with pytest.raises(Exception):
        parse_feed(b'<html>blocked</html>')
    data = b'<rss><channel><item><title>CVE-2099-1234</title><link>https://www.securitylab.ru/news/1.php</link><description>&lt;script&gt;bad&lt;/script&gt;</description></item><item><title>external</title><link>https://example.org/</link></item></channel></rss>'
    rows = parse_feed(data)
    assert len(rows) == 1 and rows[0]['summary'] == 'bad'
