"""Проверки аудита: CI, синхронизация рекомендаций, публичный интерфейс и счётчик проектов."""

import json
import os
import subprocess
import sys
from pathlib import Path

from app import app
from assistant.answer import answer_question
from assistant.knowledge import load_faqs
from cases import get_all_cases
from extensions import db
from models import Article, ArticleSource
from portal_content import PROJECTS, project_portfolio, ru_count
from project_demos import all_demos, get_demo

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def test_project_count_comes_from_one_catalog(client):
    portfolio = project_portfolio()
    case_count = len(get_all_cases())
    assert portfolio["total"] == len(PROJECTS) == 18
    assert portfolio["flagship"] == 6
    assert portfolio["quality"] == 12
    assert portfolio["total"] != case_count
    assert portfolio["total_label"] == "18 проектов"
    assert portfolio["flagship_label"] == "6 флагманов"
    assert portfolio["quality_label"] == "12 качественных проектов"

    home = client.get("/").data.decode("utf-8")
    catalog = client.get("/projects/").data.decode("utf-8")
    assert f"Смотреть {portfolio['total_label']}" in home
    assert f"Все {portfolio['total_label']}" in home
    assert "16 проектов" not in home
    assert f"Смотреть {case_count}" not in home
    assert f"Все {case_count}" not in home
    assert f"<h1>{portfolio['total_label']}</h1>" in catalog
    assert portfolio["flagship_label"] in catalog
    assert portfolio["quality_label"] in catalog
    assert "шесть флагманов" not in catalog.casefold()
    assert "двенадцать" not in catalog.casefold()
    assert f"Все {portfolio['total']}" in catalog
    assert catalog.count('class="portal-project-card') == portfolio["total"]
    assert "Все 17 материалов" in home


def test_russian_counts_decline():
    assert ru_count(1, "проект", "проекта", "проектов") == "1 проект"
    assert ru_count(2, "проект", "проекта", "проектов") == "2 проекта"
    assert ru_count(11, "проект", "проекта", "проектов") == "11 проектов"
    assert ru_count(21, "проект", "проекта", "проектов") == "21 проект"


def test_public_portfolio_hides_repositories_and_keeps_actions(client, monkeypatch):
    monkeypatch.setitem(app.config, "LIFEOS_USERNAME", "lifeos-test")
    monkeypatch.setitem(app.config, "LIFEOS_PASSWORD", "test-only-password")
    paths = [
        "/",
        "/cases/",
        "/projects/",
        "/contact/",
        "/products/",
        "/directions/medicine/",
        "/directions/ai/",
        "/directions/longevity/",
    ]
    paths.extend(f"/cases/{case['slug']}/" for case in get_all_cases())
    paths.extend(demo["url"] for demo in all_demos() if demo)
    for path in paths:
        page = client.get(path)
        assert page.status_code == 200, path
        html = page.data.decode("utf-8").casefold()
        assert "github.com" not in html, path
        assert "репозитор" not in html, path
        assert 'data-track="github_click"' not in html, path

    life_os = client.get(
        "/directions/life-os/",
        auth=("lifeos-test", "test-only-password"),
    )
    assert life_os.status_code == 200
    life_html = life_os.data.decode("utf-8").casefold()
    assert "github.com" not in life_html
    assert "репозитор" not in life_html

    legalbot = client.get("/cases/legalbot/").data.decode("utf-8")
    assert "Открыть демонстрацию" in legalbot or "Обсудить" in legalbot
    assert "Связанные репозитории" not in legalbot
    projects = client.get("/projects/").data.decode("utf-8")
    assert "Открыть демонстрацию" in projects
    assert "Смотреть видео" in projects

    related = [case for case in get_all_cases() if case["related_repos"]]
    assert len(related) == 13
    assert all(case["repo_url"].startswith("https://github.com/") for case in related)
    stored = get_demo("vitalis-medical-ai")
    assert stored["repo_url"] == "https://github.com/dimitry8st-prog/Vitalis-Medical-AI"
    assert "github.com" not in client.get(stored["url"]).data.decode("utf-8")

    for item in load_faqs():
        answer = item["answer"].casefold()
        assert "github.com" not in answer
        assert "репозитор" not in answer
    legal_answer = answer_question("Что делает LegalBot?", {})
    assert "github.com" not in legal_answer["answer"].casefold()
    assert "репозитор" not in legal_answer["answer"].casefold()

    material = client.get("/materials/kak-vitalis-proveryaet-istochniki/")
    assert material.status_code == 200
    assert b"github.com/dimitry8st-prog" not in material.data
    assert b"/cases/vitalis-medical-ai/" in material.data


def test_saved_repository_source_moves_to_portal_page():
    from editorial import point_repository_sources_at_portal

    with app.app_context():
        article = Article.query.filter_by(slug="kak-vitalis-proveryaet-istochniki").one()
        source = ArticleSource(
            article=article,
            title="Внутренняя ссылка",
            url="https://github.com/dimitry8st-prog/Lending-",
        )
        db.session.add(source)
        db.session.commit()
        source_id = source.id
        try:
            assert point_repository_sources_at_portal() >= 1
            db.session.commit()
            refreshed = db.session.get(ArticleSource, source_id)
            assert refreshed.url == "/cases/psychologist-landing/"
            assert "github.com" not in refreshed.url
        finally:
            leftover = db.session.get(ArticleSource, source_id)
            if leftover is not None:
                db.session.delete(leftover)
                db.session.commit()


def test_workflow_files_separate_tests_from_deploy():
    portal = (WORKFLOWS / "portal-tests.yml").read_text(encoding="utf-8")
    deploy = (WORKFLOWS / "deploy.yml").read_text(encoding="utf-8")
    sync = (WORKFLOWS / "sync-clinical-guidelines.yml").read_text(encoding="utf-8")
    publisher = (ROOT / "scripts" / "open_clinical_guidelines_pr.py").read_text(encoding="utf-8")

    assert "name: portal-tests" in portal
    assert "\n  pull_request:" in portal
    assert "pip install -r requirements.txt" in portal
    assert "python -m pytest -q" in portal
    for forbidden in ("docker", "ssh", "SSH_HOST", "appleboy", "ghcr.io", "TELEGRAM_", "secrets."):
        assert forbidden not in portal

    trigger, jobs = deploy.split("jobs:", 1)
    assert "\n  pull_request:" not in trigger
    assert "push:" in trigger and "workflow_dispatch:" in trigger
    assert jobs.index("  test:") < jobs.index("  build:") < jobs.index("  deploy:")
    assert "needs: test" in jobs and "needs: build" in jobs

    assert 'cron: "30 3 * * 1"' in sync
    assert "workflow_dispatch:" in sync
    assert "python -m pytest -q" in sync
    assert "open_clinical_guidelines_pr.py" in sync
    assert "HEAD:main" not in sync
    assert "HEAD:main" not in publisher
    assert "automation/clinical-guidelines" in publisher
    assert "Approve workflows to run" in publisher


def _git(repo: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=check,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if check and result.returncode != 0:
        raise AssertionError(result.stderr)
    return result.stdout.strip()


def _init_repo(tmp_path: Path) -> Path:
    origin = tmp_path / "origin.git"
    work = tmp_path / "work"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(origin)], check=True, capture_output=True)
    subprocess.run(["git", "init", "-b", "main", str(work)], check=True, capture_output=True)
    _git(work, "config", "user.email", "test@example.com")
    _git(work, "config", "user.name", "Portal Test")
    _git(work, "config", "core.autocrlf", "false")
    _git(work, "config", "core.quotepath", "false")
    notes = work / "obsidian-vault" / "Клинические рекомендации" / "Входящие"
    notes.mkdir(parents=True)
    (work / "data").mkdir()
    (work / "data" / "clinical_guidelines.json").write_text('{"items":[]}\n', encoding="utf-8")
    (notes / "minzdrav-1.md").write_text("# карточка\n", encoding="utf-8")
    (work / "README.md").write_text("readme\n", encoding="utf-8")
    _git(work, "add", ".")
    _git(work, "commit", "-m", "base")
    _git(work, "remote", "add", "origin", str(origin))
    _git(work, "push", "-u", "origin", "main")
    return work


def _install_fake_gh(directory: Path) -> None:
    script = directory / "gh.py"
    script.write_text(
        "\n".join(
            [
                "import json, os, sys",
                "from pathlib import Path",
                "log = Path(os.environ['FAKE_GH_LOG'])",
                "state = Path(os.environ['FAKE_GH_STATE'])",
                "args = sys.argv[1:]",
                "with log.open('a', encoding='utf-8') as handle:",
                "    handle.write(json.dumps(args, ensure_ascii=False) + '\\n')",
                "if args[:2] == ['pr', 'list']:",
                "    numbers = json.loads(state.read_text(encoding='utf-8')) if state.exists() else []",
                "    print(json.dumps([{'number': number} for number in numbers]))",
                "    raise SystemExit(0)",
                "if args[:2] == ['pr', 'create']:",
                "    numbers = json.loads(state.read_text(encoding='utf-8')) if state.exists() else []",
                "    number = max(numbers) + 1 if numbers else 41",
                "    numbers.append(number)",
                "    state.write_text(json.dumps(numbers), encoding='utf-8')",
                "    print(f'https://example.test/pull/{number}')",
                "    raise SystemExit(0)",
                "sys.stderr.write('unexpected gh command\\n')",
                "raise SystemExit(1)",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (directory / "gh.cmd").write_text(
        f'@echo off\r\n"{sys.executable}" "{script}" %*\r\n',
        encoding="utf-8",
    )
    posix = directory / "gh"
    posix.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n', encoding="utf-8")
    posix.chmod(0o755)


def _publisher():
    sys.path.insert(0, str(ROOT / "scripts"))
    import open_clinical_guidelines_pr as publisher

    return publisher


def _gh_log(path: Path) -> list[list[str]]:
    if not path.exists() or not path.read_text(encoding="utf-8").strip():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_guideline_pr_scenarios(tmp_path, monkeypatch):
    work = _init_repo(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _install_fake_gh(bin_dir)
    log = tmp_path / "gh.log"
    state = tmp_path / "gh-state.json"
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("FAKE_GH_LOG", str(log))
    monkeypatch.setenv("FAKE_GH_STATE", str(state))
    publisher = _publisher()
    main_sha = _git(work, "rev-parse", "main")

    assert publisher.publish(work) == "noop"
    assert _gh_log(log) == []
    assert _git(work, "ls-remote", "origin", f"refs/heads/{publisher.BRANCH}") == ""

    (work / "README.md").write_text("не для pull request\n", encoding="utf-8")
    assert publisher.publish(work) == "noop"
    assert _git(work, "rev-parse", "main") == main_sha

    registry = work / "data" / "clinical_guidelines.json"
    registry.write_text('{"items":[{"external_id":"1"}]}\n', encoding="utf-8")
    note = work / "obsidian-vault" / "Клинические рекомендации" / "Входящие" / "minzdrav-1.md"
    note.write_text("# обновлённая карточка\n", encoding="utf-8")
    outside = work / "obsidian-vault" / "посторонняя.md"
    outside.write_text("не карточка рекомендации\n", encoding="utf-8")

    assert publisher.publish(work) == "created"
    pushed = _git(work, "ls-remote", "origin", f"refs/heads/{publisher.BRANCH}")
    assert pushed
    pushed_sha = pushed.split()[0]
    names = _git(work, "diff", "--name-only", main_sha, pushed_sha).splitlines()
    assert sorted(names) == [
        "data/clinical_guidelines.json",
        "obsidian-vault/Клинические рекомендации/Входящие/minzdrav-1.md",
    ]
    assert _git(work, "rev-parse", "main") == main_sha
    assert _git(work, "ls-remote", "origin", "refs/heads/main").split()[0] == main_sha
    created = [args for args in _gh_log(log) if args[:2] == ["pr", "create"]]
    assert len(created) == 1

    same = publisher.publish(work)
    assert same == "unchanged"
    assert [args for args in _gh_log(log) if args[:2] == ["pr", "create"]] == created
    assert _git(work, "ls-remote", "origin", f"refs/heads/{publisher.BRANCH}").split()[0] == pushed_sha

    registry.write_text('{"items":[{"external_id":"2"}]}\n', encoding="utf-8")
    assert publisher.publish(work) == "updated"
    updated_sha = _git(work, "ls-remote", "origin", f"refs/heads/{publisher.BRANCH}").split()[0]
    assert updated_sha != pushed_sha
    assert _git(work, "rev-parse", f"{updated_sha}^") == main_sha
    assert len([args for args in _gh_log(log) if args[:2] == ["pr", "create"]]) == 1
    assert json.loads(state.read_text(encoding="utf-8")) == [41]
    assert _git(work, "rev-parse", "main") == main_sha


def test_guideline_pr_uses_existing_request_without_duplicate(tmp_path, monkeypatch):
    work = _init_repo(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _install_fake_gh(bin_dir)
    log = tmp_path / "gh-existing.log"
    state = tmp_path / "gh-existing.json"
    state.write_text("[7]", encoding="utf-8")
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("FAKE_GH_LOG", str(log))
    monkeypatch.setenv("FAKE_GH_STATE", str(state))
    publisher = _publisher()
    (work / "data" / "clinical_guidelines.json").write_text('{"items":[{"external_id":"9"}]}\n', encoding="utf-8")
    assert publisher.publish(work) == "updated"
    assert [args for args in _gh_log(log) if args[:2] == ["pr", "create"]] == []
    assert json.loads(state.read_text(encoding="utf-8")) == [7]
