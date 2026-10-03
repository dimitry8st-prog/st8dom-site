"""Public showcase uses the portal's existing protected inquiry flow."""
from uuid import uuid4

from app import app
from extensions import db
from models import Inquiry


def test_public_psychologist_demo_and_catalogue(client):
    page = client.get('/demos/psychologist/')
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert 'вымышленный специалист' in html
    assert 'Вымышленные примеры отзывов' in html
    assert 'action="/contact/"' in html
    assert 'method="post"' in html
    assert 'value="website" selected' in html or 'selected value="website"' in html
    assert '<script' not in html
    assert 'tel:+79991234567' not in html
    assert 'form-action' in page.headers['Content-Security-Policy']
    assert client.get('/static/demos/psychologist/style.css').status_code == 200
    assert client.get('/static/demos/psychologist/cover.webp').status_code == 200
    assert b'psychologist-landing' in client.get('/cases/').data
    assert b'/cases/psychologist-landing/' in client.get('/projects/').data
    detail = client.get('/cases/psychologist-landing/').get_data(as_text=True)
    assert 'https://st8dom.ru/demos/psychologist/' in detail
    assert 'topic=website' in detail
    assert b'/demos/psychologist/' in client.get('/sitemap.xml').data
    contact = client.get('/contact/?project=psychologist-landing').get_data(as_text=True)
    assert 'Хочу адаптировать лендинг психолога' in contact


def test_psychologist_inquiry_is_saved_and_invalid_consent_is_rejected(client, monkeypatch):
    monkeypatch.setattr('app.notify_email', lambda *args: False)
    monkeypatch.setattr('app.notify_telegram', lambda *args: None)
    monkeypatch.setattr('app.send_price_auto_reply', lambda *args: None)
    email = f'website-{uuid4().hex}@example.com'
    data = dict(name='Тестовый заказчик', email=email, phone='+7 900 000-00-00', topic='website', message='Хочу адаптировать лендинг психолога для своей практики.')
    try:
        assert client.post('/contact/', data=data).status_code == 200
        with app.app_context():
            assert Inquiry.query.filter_by(email=email).count() == 0
        response = client.post('/contact/', data={**data, 'consent': 'y'}, environ_overrides={'REMOTE_ADDR': '198.51.100.151'})
        assert response.status_code == 302
        assert response.location.endswith('/contact/?sent=1')
        with app.app_context():
            saved = Inquiry.query.filter_by(email=email).one()
            assert saved.topic == 'website'
            assert saved.message == data['message']
    finally:
        with app.app_context():
            Inquiry.query.filter_by(email=email).delete()
            db.session.commit()


def test_demo_form_csrf_is_required(client):
    previous = app.config['WTF_CSRF_ENABLED']
    app.config['WTF_CSRF_ENABLED'] = True
    try:
        assert b'name="csrf_token"' in client.get('/demos/psychologist/').data
        assert client.post('/contact/', data={'topic': 'website', 'consent': 'y'}).status_code == 400
    finally:
        app.config['WTF_CSRF_ENABLED'] = previous
