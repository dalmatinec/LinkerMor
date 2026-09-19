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


# ─── Тексты не должны быть захардкожены ──────────────────────────────────────

import ast  # noqa: E402

#: Методы, которые отправляют текст пользователю.
SENDING_METHODS = frozenset(
    {"answer", "reply", "send_message", "edit_text", "edit_message_text", "answer_photo"}
)

#: Папки, которых правило не касается: тесты и служебные скрипты.
TEXT_RULE_EXEMPT = {"tests", "migrations", "migrations_versions"}


class _HardcodedTextVisitor(ast.NodeVisitor):
    """Ищет строковые литералы, уходящие пользователю в обход Custom Texts."""

    def __init__(self) -> None:
        self.findings: list[tuple[int, str]] = []

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802 - имя из ast
        method = getattr(node.func, "attr", None)
        if method in SENDING_METHODS:
            literal = self._literal_argument(node)
            if literal is not None:
                self.findings.append((node.lineno, literal))
        self.generic_visit(node)

    @staticmethod
    def _literal_argument(node: ast.Call) -> str | None:
        if node.args and isinstance(node.args[0], ast.Constant):
            value = node.args[0].value
            if isinstance(value, str) and value.strip():
                return value
        for keyword in node.keywords:
            if keyword.arg == "text" and isinstance(keyword.value, ast.Constant):
                value = keyword.value.value
                if isinstance(value, str) and value.strip():
                    return value
        return None


def test_no_hardcoded_user_facing_text(project_root: Path) -> None:
    """Всё, что видит пользователь, приходит из системы текстов (§32.17).

    Строка, написанная прямо в хендлере, не может быть переведена, изменена
    администратором и не поддерживает премиум-эмодзи.
    """
    offenders: list[str] = []
    for path in _source_files(project_root):
        relative = path.relative_to(project_root)
        if relative.parts[0] in TEXT_RULE_EXEMPT:
            continue

        visitor = _HardcodedTextVisitor()
        visitor.visit(ast.parse(path.read_text(encoding="utf-8")))
        offenders.extend(f"{relative}:{line} — {text!r}" for line, text in visitor.findings)

    assert not offenders, "Тексты в обход Custom Texts:\n" + "\n".join(offenders)


def test_every_registered_text_is_used_in_code(project_root: Path) -> None:
    """Объявленный текст обязан где-то использоваться.

    Иначе реестр со временем зарастает ключами, которых не увидит никто.
    """
    import sys

    sys.path.insert(0, str(project_root))
    from core.bootstrap import ENABLED_MODULES
    from texts.defs import build_registry

    registry = build_registry(ENABLED_MODULES())
    sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in _source_files(project_root)
        if path.relative_to(project_root).parts[0] not in {"tests", "texts"}
    )

    unused = [
        key
        for key in registry.keys
        if not registry.get(key).dynamic and f'"{key}"' not in sources
    ]
    assert not unused, f"Тексты объявлены, но не используются: {unused}"


def test_default_texts_use_only_known_placeholders(project_root: Path) -> None:
    """Плейсхолдер-опечатка в тексте по умолчанию оставила бы пустое место.

    Проверка касается и текстов-подсказок: фигурные скобки в них
    подставляются так же, как в обычных сообщениях.
    """
    import sys

    sys.path.insert(0, str(project_root))
    from core.bootstrap import ENABLED_MODULES
    from texts.defs import build_registry
    from texts.entities import EntityText
    from texts.placeholders import unknown_placeholders

    registry = build_registry(ENABLED_MODULES())
    broken = {
        key: sorted(unknown)
        for key in registry.keys
        if (unknown := unknown_placeholders(EntityText(text=registry.get(key).default)))
    }

    assert not broken, f"Неизвестные плейсхолдеры в текстах по умолчанию: {broken}"


def test_callback_data_fits_telegram_limit(project_root: Path) -> None:
    """Telegram отвергает callback_data длиннее 64 байт.

    Проверяются самые длинные реальные сочетания модуля и ключа: если
    новый модуль назовут слишком длинно, тест упадёт до того, как кнопка
    перестанет работать у людей.
    """
    import sys

    sys.path.insert(0, str(project_root))
    from core.bootstrap import ENABLED_MODULES
    from core.constants import CALLBACK_DATA_MAX_BYTES
    from mod_admin.callbacks import SettingAction, TextAction
    from settings.defs import build_registry as build_settings
    from texts.defs import build_registry as build_texts

    specs = ENABLED_MODULES()
    oversized: list[str] = []

    settings_registry = build_settings(specs)
    for key in settings_registry.keys:
        definition = settings_registry.get(key)
        suffix = key.split(".", 1)[1] if "." in key else key
        packed = SettingAction(module=definition.module, key=suffix, action="toggle").pack()
        if len(packed.encode("utf-8")) > CALLBACK_DATA_MAX_BYTES:
            oversized.append(packed)

    text_registry = build_texts(specs)
    for key in text_registry.keys:
        definition = text_registry.get(key)
        packed = TextAction(module=definition.module, key=key, action="open").pack()
        if len(packed.encode("utf-8")) > CALLBACK_DATA_MAX_BYTES:
            oversized.append(packed)

    assert not oversized, f"callback_data превышает лимит: {oversized}"
