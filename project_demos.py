"""Curated, offline interface examples; no model calls or external submissions."""

import json
from pathlib import Path

from cases import get_all_cases, get_case
from portal_content import PROJECTS

PROFILES = json.loads((Path(__file__).parent / 'data/project_demos.json').read_text(encoding='utf-8'))
REPO_SLUGS = {
    'KPI-Pulse': 'kpi-pulse', 'Life-Os': 'life-os', 'meeting-360': 'meeting-360',
    'MedBot-AI': 'medbot-ai', '-Lingua-360': 'lingua-360', 'QGIS-': 'sar-gpt-analyzer',
    'OnboardFlow_AI': 'onboardflow-ai',
}
EXTRA_STATUS = {
    'kpi-pulse': ('Локальный MVP', 'CSV, расчёт KPI, дашборд и дайджест описаны в репозитории. На этой странице доступны учебные примеры.'),
    'life-os': ('Локальная система знаний', 'В репозитории описаны захват материалов, заметки Obsidian и локальный поиск. Личное хранилище к публичному демо не подключено.'),
    'medbot-ai': ('Проектирование / интерфейсный концепт', 'README описывает архитектуру и план модулей. Готовность клинических функций на этой странице не заявляется.'),
    'sar-gpt-analyzer': ('Плагин: базовая обработка / AI в плане', 'README подтверждает проверку растров и перевод в дБ; интеграция AI отмечена как план. В браузере растры не обрабатываются.'),
}


def project_demo_slug(project):
    return project.get('case_slug') or REPO_SLUGS.get(project['repo'])


def demo_url(slug):
    return '/demos/psychologist/' if slug == 'psychologist-landing' else f'/demos/{slug}/'


def get_demo(slug):
    case = get_case(slug)
    project = next((p for p in PROJECTS if project_demo_slug(p) == slug), None)
    if not case and not project:
        return None
    if slug != 'psychologist-landing' and slug not in PROFILES:
        return None
    profile = PROFILES.get(slug, {})
    status, limits = EXTRA_STATUS.get(slug, ('Демонстрационный сценарий', 'Рабочий сервис к этой странице не подключён.'))
    return {
        **profile, 'slug': slug,
        'name': case['short_title'] if case else project['name'],
        'summary': case['card_summary'] if case else project['summary'],
        'image': case['image'] if case else 'og-cover.svg',
        'image_alt': case['image_alt'] if case else f"Демонстрация проекта {project['name']} на портале ДИС",
        'repo_url': (case.get('repo_url') if case else None) or (f"https://github.com/dimitry8st-prog/{project['repo']}" if project else None),
        'case_slug': case['slug'] if case else None,
        'status': case['status'] if case else status,
        'limitations': case['limitations'] if case else limits,
        'current': case['now_works'] if case else limits,
        'topic': 'website' if slug in {'elan', 'corporate-site', 'psychologist-landing'} else 'integration',
        'url': demo_url(slug),
    }


def all_demos():
    return [get_demo(slug) for slug in ['psychologist-landing', *PROFILES]]


def catalog_with_demos():
    return [{**p, 'demo_url': demo_url(project_demo_slug(p))} for p in PROJECTS]
