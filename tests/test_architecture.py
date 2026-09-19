"""Архитектурные тесты: правила проекта проверяются автоматически.

Эти тесты стерегут договорённости, которые иначе нарушаются незаметно
по мере роста кодовой базы.
"""

from __future__ import annotations

from pathlib import Path

IGNORED_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", "docs"}


def _source_files(root: Path) -> list[Path]:
    return [
        path
        for path in root.rglob("*.py")
        if not any(part in IGNORED_DIRS for part in path.relative_to(root).parts)
    ]


def test_project_depth_never_exceeds_two_levels(project_root: Path) -> None:
    """Структура ограничена схемой root → folder → file (ТЗ §25)."""
    too_deep = [
        str(path.relative_to(project_root))
        for path in _source_files(project_root)
        if len(path.relative_to(project_root).parts) > 2
    ]
    assert not too_deep, f"Слишком глубокая вложенность: {too_deep}"


def test_env_file_is_ignored_by_git(project_root: Path) -> None:
    """Секреты не должны попадать в репозиторий (ТЗ §29)."""
    ignored = (project_root / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".env" in ignored


def test_example_env_has_no_real_token(project_root: Path) -> None:
    example = (project_root / ".env.example").read_text(encoding="utf-8")
    assert "REPLACE_ME" in example
    for line in example.splitlines():
        if line.startswith("BOT_TOKEN="):
            assert "REPLACE_ME" in line


def test_cache_keys_module_exposes_no_global_chat_key(project_root: Path) -> None:
    """В проекте не должно появиться функции, строящей ключ чата без chat_id."""
    source = (project_root / "cache" / "keys.py").read_text(encoding="utf-8")
    assert "def chat_key(entity: ChatEntity, chat_id: int" in source
