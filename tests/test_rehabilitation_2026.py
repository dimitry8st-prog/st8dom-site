"""Публикация обзора и разделение рекомендаций по официальным источникам."""

from app import app
from editorial import ensure_editorial_seed
from models import Article, ClinicalGuideline


def test_rehabilitation_review_is_public_and_in_correct_rubric(client):
    slug = "reabilitaciya-posle-insulta-2026"
    detail = client.get(f"/materials/{slug}/")
    assert detail.status_code == 200
    assert "Когда нужна срочная помощь".encode() in detail.data
    assert "Полный текст руководства не был доступен для проверки".encode() in detail.data
    assert "Черновик для редакционной проверки".encode() not in detail.data
    with app.app_context():
        ensure_editorial_seed()
        assert Article.query.filter_by(slug=slug).count() == 1
        article = Article.query.filter_by(slug=slug).one()
        assert article.status == "published"
        assert article.rubric.slug == "rehabilitation-after-stroke"
        assert len(article.sources) == 8
    assert slug.encode() in client.get("/directions/medicine/rehabilitation/").data
    assert slug.encode() in client.get("/materials/?section=medicine&rubric=rehabilitation-after-stroke").data


def test_stroke_guidelines_are_classified_and_visible_in_rehabilitation(client):
    with app.app_context():
        for source, external_id in [
            ("aha_asa", "AHA-ASA-STROKE-REHABILITATION-2026"),
            ("canadian_stroke", "CSBPR-REHABILITATION-MOBILITY-2025"),
        ]:
            record = ClinicalGuideline.query.filter_by(source_key=source, external_id=external_id).one()
            assert record.kind == "international"
    rehab = client.get("/directions/medicine/rehabilitation/")
    assert rehab.status_code == 200
    assert "Российские рекомендации".encode() in rehab.data
    assert "Международные рекомендации".encode() in rehab.data
    assert b"2026-guideline-for-adult-stroke-rehabilitation-and-recovery" in rehab.data
    assert b"4-lower-extremity-balance-mobility-and-aerobic-training" in rehab.data
    assert b"523_3" in rehab.data
    international = client.get("/clinical-guidelines/?kind=international&q=инсульт")
    russian = client.get("/clinical-guidelines/?kind=russian&q=инсульт")
    assert b"2026-guideline-for-adult-stroke-rehabilitation-and-recovery" in international.data
    assert b"2026-guideline-for-adult-stroke-rehabilitation-and-recovery" not in russian.data
    assert b"523_3" in russian.data
