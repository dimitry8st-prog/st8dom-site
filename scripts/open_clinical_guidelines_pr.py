"""Кладёт обновление клинических рекомендаций в один pull request.

Скрипт не пушит в main. Ветка automation/clinical-guidelines каждый раз
становится одним коммитом поверх origin/main, поэтому повторный запуск
обновляет тот же pull request и не создаёт второй.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

BRANCH = "automation/clinical-guidelines"
BASE_BRANCH = "main"
REGISTRY = "data/clinical_guidelines.json"
NOTES_PREFIX = "obsidian-vault/Клинические рекомендации/Входящие/"
COMMIT_MESSAGE = "Обновить клинические рекомендации"
PR_TITLE = "Обновить клинические рекомендации"
PR_BODY = """Автоматическое обновление реестра клинических рекомендаций и карточек Obsidian.

Перед объединением изменения нужно просмотреть вручную: это медицинские сведения, и workflow не публикует их сам.

В коммите только `data/clinical_guidelines.json` и заметки в `obsidian-vault/Клинические рекомендации/Входящие/`. Повторный запуск обновляет эту ветку и этот pull request, а не открывает новый.

Workflow не отправляет коммит в `main`. После объединения обычный push в `main` запускает существующий деплой.

Проверка `portal-tests` для pull request, созданного `GITHUB_TOKEN`, появляется в состоянии ожидания. Её запускает человек с правом записи кнопкой Approve workflows to run. Без отдельного PAT или токена GitHub App автоматический запуск этой проверки не обещается.
"""


def is_allowed(path: str) -> bool:
    normalized = path.replace("\\", "/")
    return normalized == REGISTRY or normalized.startswith(NOTES_PREFIX)


def run(
    args: list[str],
    cwd: Path,
    *,
    env: dict[str, str] | None = None,
    check: bool = True,
    input_bytes: bytes | None = None,
) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(
        args,
        cwd=cwd,
        env=env,
        input=input_bytes,
        capture_output=True,
        check=False,
    )
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout).decode("utf-8", errors="replace").strip()
        raise SystemExit(f"{' '.join(args)} завершился с кодом {result.returncode}: {detail}")
    return result


def git(
    repo: Path,
    *args: str,
    env: dict[str, str] | None = None,
    check: bool = True,
    input_bytes: bytes | None = None,
) -> str:
    result = run(
        ["git", "-C", str(repo), *args],
        repo,
        env=env,
        check=check,
        input_bytes=input_bytes,
    )
    return result.stdout.decode("utf-8", errors="replace")


def parse_status(raw: bytes) -> list[tuple[str, str]]:
    parts = raw.split(b"\0")
    if parts and parts[-1] == b"":
        parts.pop()
    entries: list[tuple[str, str]] = []
    index = 0
    while index < len(parts):
        record = parts[index]
        status = record[:2].decode("ascii", errors="replace")
        path = record[3:].decode("utf-8")
        index += 1
        if status[:1] in {"R", "C"}:
            path = parts[index].decode("utf-8")
            index += 1
        entries.append((status, path.replace("\\", "/")))
    return entries


def allowed_changes(repo: Path) -> dict[str, bytes | None]:
    raw = run(
        ["git", "-C", str(repo), "status", "--porcelain=v1", "-z", "--untracked-files=all"],
        repo,
    ).stdout
    changes: dict[str, bytes | None] = {}
    for status, path in parse_status(raw):
        if not is_allowed(path):
            continue
        full = repo / path
        if "D" in status or not full.exists():
            changes[path] = None
        else:
            changes[path] = full.read_bytes()
    return changes


def base_commit(repo: Path) -> str:
    run(["git", "-C", str(repo), "fetch", "origin", BASE_BRANCH], repo)
    return git(repo, "rev-parse", f"origin/{BASE_BRANCH}").strip()


def build_commit(repo: Path, base: str, changes: dict[str, bytes | None]) -> str | None:
    index_dir = Path(tempfile.mkdtemp(prefix="guidelines-index-"))
    index_path = index_dir / "index"
    env = os.environ.copy()
    env["GIT_INDEX_FILE"] = str(index_path)
    git(repo, "read-tree", base, env=env)
    for path, content in changes.items():
        if content is None:
            present = run(
                ["git", "-C", str(repo), "cat-file", "-e", f"{base}:{path}"],
                repo,
                check=False,
            )
            if present.returncode == 0:
                git(repo, "update-index", "--force-remove", "--", path, env=env)
            continue
        blob = git(repo, "hash-object", "-w", "--stdin", input_bytes=content).strip()
        git(repo, "update-index", "--add", "--cacheinfo", "100644", blob, path, env=env)
    tree = git(repo, "write-tree", env=env).strip()
    base_tree = git(repo, "rev-parse", f"{base}^{{tree}}").strip()
    if tree == base_tree:
        return None
    names = git(
        repo,
        "-c",
        "core.quotepath=false",
        "diff",
        "--name-only",
        base,
        tree,
    ).splitlines()
    unexpected = [name for name in names if name and not is_allowed(name)]
    if unexpected:
        raise SystemExit("Коммит затронул пути вне реестра и карточек: " + ", ".join(unexpected))
    commit = git(
        repo,
        "-c",
        "user.name=DIS Clinical Guidelines Bot",
        "-c",
        "user.email=actions@users.noreply.github.com",
        "commit-tree",
        tree,
        "-p",
        base,
        "-m",
        COMMIT_MESSAGE,
    ).strip()
    return commit


def remote_branch(repo: Path) -> str:
    result = run(
        ["git", "-C", str(repo), "ls-remote", "origin", f"refs/heads/{BRANCH}"],
        repo,
    )
    line = result.stdout.decode("utf-8", errors="replace").strip()
    return line.split()[0] if line else ""


def push_commit(repo: Path, commit: str) -> None:
    current = remote_branch(repo)
    if not current:
        run(
            ["git", "-C", str(repo), "push", "origin", f"{commit}:refs/heads/{BRANCH}"],
            repo,
        )
        return
    run(["git", "-C", str(repo), "fetch", "origin", f"refs/heads/{BRANCH}"], repo)
    parent = git(repo, "rev-parse", f"{current}^").strip()
    remote_tree = git(repo, "rev-parse", f"{current}^{{tree}}").strip()
    new_tree = git(repo, "rev-parse", f"{commit}^{{tree}}").strip()
    base = git(repo, "rev-parse", f"origin/{BASE_BRANCH}").strip()
    if parent == base and remote_tree == new_tree:
        return
    run(
        [
            "git",
            "-C",
            str(repo),
            "push",
            f"--force-with-lease=refs/heads/{BRANCH}:{current}",
            "origin",
            f"{commit}:refs/heads/{BRANCH}",
        ],
        repo,
    )


def gh_executable() -> str:
    found = shutil.which("gh")
    if not found:
        raise SystemExit("Команда gh не найдена")
    return found


def open_requests(repo: Path) -> list[int]:
    result = run(
        [
            gh_executable(),
            "pr",
            "list",
            "--head",
            BRANCH,
            "--base",
            BASE_BRANCH,
            "--state",
            "open",
            "--json",
            "number",
        ],
        repo,
    )
    payload = json.loads(result.stdout.decode("utf-8") or "[]")
    return [int(item["number"]) for item in payload]


def ensure_pull_request(repo: Path) -> str:
    numbers = open_requests(repo)
    if len(numbers) > 1:
        raise SystemExit("Открыто несколько pull request ветки автоматизации: " + ", ".join(map(str, numbers)))
    if numbers:
        print(f"Обновлён pull request #{numbers[0]}")
        return "updated"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".md", delete=False) as handle:
        handle.write(PR_BODY)
        body_path = handle.name
    try:
        run(
            [
                gh_executable(),
                "pr",
                "create",
                "--base",
                BASE_BRANCH,
                "--head",
                BRANCH,
                "--title",
                PR_TITLE,
                "--body-file",
                body_path,
            ],
            repo,
        )
    finally:
        Path(body_path).unlink(missing_ok=True)
    print("Создан pull request")
    return "created"


def publish(repo: Path) -> str:
    if not allowed_changes(repo):
        print("Официальный реестр не изменился")
        return "noop"
    base = base_commit(repo)
    changes = allowed_changes(repo)
    commit = build_commit(repo, base, changes)
    if commit is None:
        print("Официальный реестр не изменился")
        return "noop"
    before = remote_branch(repo)
    push_commit(repo, commit)
    after = remote_branch(repo)
    if before and before == after:
        numbers = open_requests(repo)
        if numbers:
            print(f"Pull request #{numbers[0]} уже содержит это обновление")
            return "unchanged"
    return ensure_pull_request(repo)


def main() -> None:
    print(publish(Path.cwd()))


if __name__ == "__main__":
    main()
