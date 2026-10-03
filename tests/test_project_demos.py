"""Offline demos and project-tagged inquiries share the protected portal inbox."""
import re
from uuid import uuid4

import pytest

from app import app
from cases import get_all_cases
from extensions import db
from models import AdminUser, Inquiry
from project_demos import PROFILES, all_demos, catalog_with_demos


@pytest.mark.parametrize('demo', all_demos(), ids=lambda d: d['slug'])
def test_demo_is_complete_and_form_tracks_project(client, demo):
    response = client.get(demo['url'])
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'action="/contact/"' in html
    assert re.search(r'name="project"[^>]*value="' + demo['slug'] + '"', html)
    if demo['slug'] != 'psychologist-landing':
        for anchor in ['benefits', 'example', 'process', 'faq', 'request']:
            assert f'id="{anchor}"' in html
        assert len(demo['examples']) >= 2
        for example in demo['examples']:
            assert example['input'] in html
            assert example['result'].splitlines()[0] in html
        assert 'data-demo-run' in html


def test_demo_links_cover_all_cases_and_catalog(client):
    html = client.get('/projects/').get_data(as_text=True)
    for project in catalog_with_demos():
        assert f'href="{project["demo_url"]}"' in html
    for case in get_all_cases():
        page = client.get('/cases/' + case['slug'] + '/').get_data(as_text=True)
        assert 'Открыть демонстрацию' in page
        assert 'case-hero--showcase' in page
    assert client.get('/demos/not-a-project/').status_code == 404
    assert client.post('/demos/knightcat-content-factory/').status_code == 405
    sitemap = client.get('/sitemap.xml').get_data(as_text=True)
    for demo in all_demos():
        assert demo['url'] in sitemap


def test_project_inquiry_is_saved_deduplicated_and_filterable(client, monkeypatch):
    monkeypatch.setattr('app.notify_email', lambda *args: False)
    monkeypatch.setattr('app.notify_telegram', lambda *args: None)
    monkeypatch.setattr('app.send_price_auto_reply', lambda *args: None)
    token = uuid4().hex
    email = f'demo-{token}@example.com'
    data = {'name':'Тестовый посетитель', 'email':email, 'phone':'+7 900 000-00-00',
            'topic':'integration', 'message':'Хочу обсудить внедрение в команду.',
            'consent':'y', 'project':'knightcat-content-factory'}
    try:
        assert client.post('/contact/', data=data).status_code == 302
        assert client.post('/contact/', data=data).status_code == 409
        with app.app_context():
            saved = Inquiry.query.filter_by(email=email).one()
            assert saved.message.startswith('[Проект: knightcat-content-factory — KnightCat]\n')
            admin_id = AdminUser.query.first().id
        assert client.get('/admin/?project=knightcat-content-factory').status_code == 302
        with client.session_transaction() as session:
            session['_user_id'] = str(admin_id)
            session['_fresh'] = True
        assert email.encode() in client.get('/admin/?project=knightcat-content-factory').data
        assert email.encode() not in client.get('/admin/?project=elan').data
        assert client.get('/admin/?project=unknown').status_code == 400
    finally:
        with app.app_context():
            Inquiry.query.filter_by(email=email).delete()
            db.session.commit()


def test_unknown_project_cannot_be_saved_and_known_get_is_prefilled(client, monkeypatch):
    monkeypatch.setattr('app.notify_email', lambda *args: pytest.fail('Must not send'))
    monkeypatch.setattr('app.notify_telegram', lambda *args: pytest.fail('Must not send'))
    token = uuid4().hex
    email = f'invalid-demo-{token}@example.com'
    response = client.post('/contact/', data={
        'name':'Тестовый посетитель', 'email':email, 'phone':'+7 900 000-00-00',
        'topic':'integration', 'message':'Нужна проверка проекта.', 'consent':'y', 'project':'unknown',
    })
    assert response.status_code == 200
    assert 'Неизвестный проект заявки' in response.get_data(as_text=True)
    with app.app_context():
        assert Inquiry.query.filter_by(email=email).count() == 0
    html = client.get('/contact/?project=elan').get_data(as_text=True)
    assert 'value="elan"' in html
    assert 'ÉLAN' in html


def test_demo_form_does_not_bypass_csrf(client, monkeypatch):
    monkeypatch.setitem(app.config, 'WTF_CSRF_ENABLED', True)
    assert b'name="csrf_token"' in client.get('/demos/elan/').data
    assert client.post('/contact/', data={'project':'elan', 'topic':'website', 'consent':'y'}).status_code == 400
