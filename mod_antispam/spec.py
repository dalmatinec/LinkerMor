"""Паспорт модуля антиспама."""

from __future__ import annotations

from core.registry import ModuleSpec
from mod_antispam.handlers import router
from mod_antispam.models import FilterState, ForbiddenWord, ForwardAllowance
from settings.defs import SettingDef
from texts.defs import TextDef

#: Действия, доступные правилам.
ACTIONS = ("none", "delete", "warn", "mute", "kick", "ban")


def rule_settings(
    rule: str, title: str, *, action: str = "delete", duration: int = 0, enabled: bool = False
) -> list[SettingDef]:
    """Общий набор настроек для правила.

    Все правила настраиваются одинаково, поэтому набор собирается
    функцией: добавление правила не требует переписывать список руками.
    """
    return [
        SettingDef(
            key=f"antispam.{rule}.enabled",
            default=enabled,
            type=bool,
            module="antispam",
            description=f"{title}: правило включено",
        ),
        SettingDef(
            key=f"antispam.{rule}.action",
            default=action,
            type=str,
            module="antispam",
            description=f"{title}: что делать с нарушителем",
            choices=ACTIONS,
        ),
        SettingDef(
            key=f"antispam.{rule}.duration",
            default=duration,
            type=int,
            module="antispam",
            description=f"{title}: срок наказания в секундах",
            minimum=0,
            maximum=31536000,
        ),
        SettingDef(
            key=f"antispam.{rule}.delete",
            default=True,
            type=bool,
            module="antispam",
            description=f"{title}: удалять сообщение",
        ),
    ]


SETTINGS: list[SettingDef] = [
    # Правила выключены по умолчанию: бот не должен начинать наказывать
    # людей сразу после добавления в чат.
    *rule_settings("words", "Запрещённые слова"),
    SettingDef(
        key="antispam.words.whole_only",
        default=True,
        type=bool,
        module="antispam",
        description="Запрещённые слова: искать только целые слова",
    ),
    *rule_settings("forwards", "Пересылки", action="mute", duration=3600),
    *rule_settings("links", "Ссылки"),
    SettingDef(
        key="antispam.links.telegram_only",
        default=True,
        type=bool,
        module="antispam",
        description="Ссылки: запрещать только ссылки на Telegram",
    ),
    *rule_settings("flood", "Флуд", action="mute", duration=300),
    SettingDef(
        key="antispam.flood.limit",
        default=5,
        type=int,
        module="antispam",
        description="Флуд: сколько сообщений допустимо за период",
        minimum=2,
        maximum=100,
    ),
    SettingDef(
        key="antispam.flood.window",
        default=10,
        type=int,
        module="antispam",
        description="Флуд: период наблюдения в секундах",
        minimum=1,
        maximum=3600,
    ),
    *rule_settings("caps", "Капс"),
    SettingDef(
        key="antispam.caps.percent",
        default=70,
        type=int,
        module="antispam",
        description="Капс: доля заглавных букв в процентах",
        minimum=30,
        maximum=100,
    ),
    SettingDef(
        key="antispam.caps.min_length",
        default=10,
        type=int,
        module="antispam",
        description="Капс: минимальная длина сообщения для проверки",
        minimum=1,
        maximum=500,
    ),
    *rule_settings("mentions", "Упоминания"),
    SettingDef(
        key="antispam.mentions.limit",
        default=5,
        type=int,
        module="antispam",
        description="Упоминания: сколько допустимо в одном сообщении",
        minimum=1,
        maximum=50,
    ),
    *rule_settings("media", "Вложения"),
    SettingDef(
        key="antispam.media.types",
        default="",
        type=str,
        module="antispam",
        description="Вложения: запрещённые виды через запятую",
    ),
]

TEXTS = [
    TextDef(
        key="antispam_forward",
        default=(
            "{mention}, пересылки в этом чате запрещены. "
            "Обратитесь к администраторам за разрешением."
        ),
        module="antispam",
        description="Пересылка из источника вне белого списка",
    ),
    TextDef(
        key="antispam_words",
        default="{mention}, это слово запрещено в чате.",
        module="antispam",
        description="Сработало правило запрещённых слов",
    ),
    TextDef(
        key="antispam_links",
        default="{mention}, ссылки в этом чате запрещены.",
        module="antispam",
        description="Сработало правило ссылок",
    ),
    TextDef(
        key="antispam_flood",
        default="{mention}, слишком много сообщений подряд.",
        module="antispam",
        description="Сработало правило флуда",
    ),
    TextDef(
        key="antispam_caps",
        default="{mention}, пишите без капса.",
        module="antispam",
        description="Сработало правило капса",
    ),
    TextDef(
        key="antispam_mentions",
        default="{mention}, слишком много упоминаний в одном сообщении.",
        module="antispam",
        description="Сработало правило упоминаний",
    ),
    TextDef(
        key="antispam_media",
        default="{mention}, такие вложения в этом чате запрещены.",
        module="antispam",
        description="Сработало правило вложений",
    ),
    # ─── Управление списками ─────────────────────────────────────────────────
    TextDef(key="antispam_word_added", default="Слово «{reason}» добавлено в список.",
            module="antispam", description="Слово запрещено"),
    TextDef(key="antispam_word_exists", default="Слово «{reason}» уже в списке.",
            module="antispam", description="Слово уже запрещено"),
    TextDef(key="antispam_word_removed", default="Слово «{reason}» убрано из списка.",
            module="antispam", description="Слово разрешено"),
    TextDef(key="antispam_word_missing", default="Слова «{reason}» нет в списке.",
            module="antispam", description="Слова нет в списке"),
    TextDef(key="antispam_word_usage", default="Укажите слово: /addword реклама",
            module="antispam", description="Команда вызвана без слова"),
    TextDef(key="antispam_words_list", default="Запрещено слов: {count}\n\n{items}",
            module="antispam", description="Список запрещённых слов"),
    TextDef(key="antispam_words_empty", default="Список запрещённых слов пуст.",
            module="antispam", description="Список пуст"),
    TextDef(key="antispam_forward_allowed", default="Пересылки из «{reason}» разрешены.",
            module="antispam", description="Источник добавлен в белый список"),
    TextDef(key="antispam_forward_known", default="Источник «{reason}» уже разрешён.",
            module="antispam", description="Источник уже в списке"),
    TextDef(key="antispam_forward_denied", default="Пересылки из «{reason}» снова запрещены.",
            module="antispam", description="Источник убран из белого списка"),
    TextDef(key="antispam_forward_missing", default="Источника «{reason}» нет в списке.",
            module="antispam", description="Источника нет в списке"),
    TextDef(
        key="antispam_forward_usage",
        default="Ответьте этой командой на пересланное сообщение.",
        module="antispam",
        description="Команда вызвана не ответом на пересылку",
    ),
    TextDef(
        key="antispam_forward_hidden",
        default="Отправитель скрыт настройками приватности — разрешить его нельзя.",
        module="antispam",
        description="У источника нет идентификатора",
    ),
    TextDef(key="antispam_forward_list", default="Разрешено источников: {count}\n\n{items}",
            module="antispam", description="Белый список пересылок"),
    TextDef(key="antispam_forward_empty", default="Белый список пересылок пуст.",
            module="antispam", description="Белый список пуст"),
]

#: Антиспам работает после команд модерации, но до триггеров: спам не
#: должен успеть вызвать ответ бота, а команда администратора не должна
#: попасть под фильтр.
MODULE = ModuleSpec(
    name="antispam",
    priority=60,
    router=router,
    models=(ForbiddenWord, ForwardAllowance, FilterState),
    setting_defs=tuple(SETTINGS),
    text_defs=tuple(TEXTS),
    requires_perms=("can_delete_messages",),
)
