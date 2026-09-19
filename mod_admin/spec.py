"""Паспорт модуля админ-панели."""

from __future__ import annotations

from core.registry import ModuleSpec
from mod_admin.handlers import router
from texts.defs import TextDef

TEXTS = [
    # ─── Выбор чата ──────────────────────────────────────────────────────────
    TextDef(
        key="admin_select_chat",
        default="Выберите чат для настройки. Доступно чатов: {count}",
        module="admin",
        description="Заголовок списка чатов",
    ),
    TextDef(
        key="admin_no_chats",
        default=(
            "Вы не администрируете ни одного чата с этим ботом.\n\n"
            "Добавьте бота в свой чат и выдайте ему права администратора."
        ),
        module="admin",
        description="Человеку нечего настраивать",
    ),
    # ─── Главное меню ────────────────────────────────────────────────────────
    TextDef(
        key="admin_menu",
        default="Настройка чата «{chat_title}»\n\nВыберите раздел:",
        module="admin",
        description="Главное меню чата",
    ),
    TextDef(
        key="admin_modules",
        default="Модули этого чата. Нажмите, чтобы включить или выключить.",
        module="admin",
        description="Экран модулей",
    ),
    TextDef(
        key="admin_settings",
        default="Настройки. Выберите раздел:",
        module="admin",
        description="Экран разделов настроек",
    ),
    TextDef(
        key="admin_module_settings",
        default="Настройки раздела «{module}»:",
        module="admin",
        description="Настройки одного модуля",
    ),
    TextDef(
        key="admin_texts",
        default="Тексты бота. Выберите раздел:",
        module="admin",
        description="Экран разделов текстов",
    ),
    TextDef(
        key="admin_module_texts",
        default="Тексты раздела «{module}». Изменённые отмечены значком.",
        module="admin",
        description="Тексты одного модуля",
    ),
    # ─── Настройка ───────────────────────────────────────────────────────────
    TextDef(
        key="admin_setting_view",
        default="{description}\n\nКлюч: {setting}\nТекущее значение: {value}",
        module="admin",
        description="Экран одной настройки",
    ),
    TextDef(
        key="admin_setting_prompt",
        default="Пришлите новое значение для настройки «{description}».\n\n"
        "Отменить — /cancel",
        module="admin",
        description="Запрос нового значения настройки",
    ),
    TextDef(
        key="admin_setting_invalid",
        default="Значение не подходит: {reason}\n\nПопробуйте ещё раз или /cancel",
        module="admin",
        description="Введённое значение не прошло проверку",
    ),
    # ─── Текст ───────────────────────────────────────────────────────────────
    TextDef(
        key="admin_text_view",
        default="{description}\n\nКлюч: {setting}\nИсточник: {source}\n\n"
        "Текущее значение — в следующем сообщении.",
        module="admin",
        description="Экран одного текста",
    ),
    TextDef(
        key="admin_text_prompt",
        default=(
            "Пришлите новый текст для «{description}».\n\n"
            "Форматирование и премиум-эмодзи сохранятся. "
            "Плейсхолдеры подставятся при отправке.\n\nОтменить — /cancel"
        ),
        module="admin",
        description="Запрос нового текста",
    ),
    TextDef(
        key="admin_text_invalid",
        default="Текст не сохранён: {reason}\n\nПопробуйте ещё раз или /cancel",
        module="admin",
        description="В тексте неизвестный плейсхолдер",
    ),
    TextDef(
        key="admin_cancelled",
        default="Отменено.",
        module="admin",
        description="Ввод прерван",
    ),
    # ─── Содержимое чата ─────────────────────────────────────────────────────
    TextDef(
        key="admin_content",
        default="Содержимое чата. Всё настраивается здесь, команды в группе не нужны.",
        module="admin",
        description="Экран раздела содержимого",
    ),
    TextDef(
        key="admin_welcome_set",
        default="Приветствие настроено. Ниже — как его увидят новички.",
        module="admin",
        description="Приветствие задано",
    ),
    TextDef(
        key="admin_welcome_default",
        default="Своё приветствие не задано, используется стандартное.",
        module="admin",
        description="Приветствие не задано",
    ),
    TextDef(
        key="admin_welcome_prompt",
        default=(
            "Пришлите сообщение, которое станет приветствием.\n\n"
            "Можно с картинкой, форматированием и премиум-эмодзи. "
            "Плейсхолдеры подставятся при отправке.\n\nОтменить — /cancel"
        ),
        module="admin",
        description="Запрос нового приветствия",
    ),
    TextDef(
        key="admin_welcome_invalid",
        default="Не удалось сохранить приветствие: {reason}",
        module="admin",
        description="Сообщение не подходит для приветствия",
    ),
    TextDef(
        key="admin_words_list",
        default="Запрещено слов: {count}. Нажмите на слово, чтобы убрать его.",
        module="admin",
        description="Список запрещённых слов в панели",
    ),
    TextDef(
        key="admin_words_empty",
        default="Список запрещённых слов пуст.",
        module="admin",
        description="Запрещённых слов нет",
    ),
    TextDef(
        key="admin_word_prompt",
        default=(
            "Пришлите слово, которое нужно запретить.\n\n"
            "Можно несколько — каждое с новой строки.\n\nОтменить — /cancel"
        ),
        module="admin",
        description="Запрос запрещённого слова",
    ),
    TextDef(
        key="admin_forwards_list",
        default="Разрешено источников: {count}. Нажмите, чтобы убрать из списка.",
        module="admin",
        description="Белый список пересылок в панели",
    ),
    TextDef(
        key="admin_forwards_empty",
        default=(
            "Белый список пуст: пересылки запрещены полностью, "
            "если правило включено."
        ),
        module="admin",
        description="Белый список пуст",
    ),
    TextDef(
        key="admin_forward_prompt",
        default=(
            "Перешлите сюда сообщение из канала, который нужно разрешить.\n\n"
            "Либо пришлите @username канала или его числовой идентификатор.\n\n"
            "Отменить — /cancel"
        ),
        module="admin",
        description="Запрос источника пересылок",
    ),
    TextDef(
        key="admin_forward_unknown",
        default=(
            "Не удалось определить источник. Перешлите сообщение из канала "
            "или пришлите его @username."
        ),
        module="admin",
        description="Источник не распознан",
    ),
    # ─── Подписи кнопок ──────────────────────────────────────────────────────
    TextDef(key="admin_btn_modules", default="Модули", module="admin",
            description="Кнопка: модули"),
    TextDef(key="admin_btn_settings", default="Настройки", module="admin",
            description="Кнопка: настройки"),
    TextDef(key="admin_btn_texts", default="Тексты", module="admin",
            description="Кнопка: тексты"),
    TextDef(key="admin_btn_content", default="Содержимое", module="admin",
            description="Кнопка: приветствие, слова, пересылки"),
    TextDef(key="admin_btn_welcome", default="Приветствие", module="admin",
            description="Кнопка: приветствие"),
    TextDef(key="admin_btn_words", default="Запрещённые слова", module="admin",
            description="Кнопка: запрещённые слова"),
    TextDef(key="admin_btn_forwards", default="Белый список пересылок", module="admin",
            description="Кнопка: белый список пересылок"),
    TextDef(key="admin_btn_add", default="Добавить", module="admin",
            description="Кнопка: добавить элемент списка"),
    TextDef(key="admin_btn_chats", default="Другой чат", module="admin",
            description="Кнопка: вернуться к списку чатов"),
    TextDef(key="admin_btn_back", default="Назад", module="admin",
            description="Кнопка: назад"),
    TextDef(key="admin_btn_edit", default="Изменить", module="admin",
            description="Кнопка: изменить значение"),
    TextDef(key="admin_btn_reset", default="Сбросить", module="admin",
            description="Кнопка: вернуть значение по умолчанию"),
    TextDef(key="admin_btn_toggle", default="Переключить", module="admin",
            description="Кнопка: переключить настройку"),
    TextDef(key="admin_btn_on", default="включено", module="admin",
            description="Состояние: включено"),
    TextDef(key="admin_btn_off", default="выключено", module="admin",
            description="Состояние: выключено"),
    TextDef(key="admin_btn_prev", default="Назад", module="admin",
            description="Кнопка: предыдущая страница"),
    TextDef(key="admin_btn_next", default="Вперёд", module="admin",
            description="Кнопка: следующая страница"),
]

#: Панель работает в личке и не конкурирует с обработкой групповых
#: сообщений, поэтому её место в цепочке роли почти не играет. Ставим
#: раньше модерации, чтобы команды панели не перехватывались.
MODULE = ModuleSpec(
    name="admin",
    priority=30,
    router=router,
    text_defs=tuple(TEXTS),
    can_disable=False,  # без панели чат нечем настраивать
)
