"""Паспорт модуля админ-панели."""

from __future__ import annotations

from core.registry import ModuleSpec
from mod_admin.handlers import router
from texts.defs import TextDef

TEXTS = [
    # ─── Стартовый экран ─────────────────────────────────────────────────────
    TextDef(
        key="start_greeting",
        default=(
            "Привет, {user}!\n"
            "\n"
            "Я помогаю держать порядок в группах. Ловлю спам и рекламу, "
            "встречаю новичков, проверяю их на входе, веду репутацию и ранги, "
            "отвечаю на ключевые слова.\n"
            "\n"
            "Всё настраивается прямо здесь, в личных сообщениях. Заходить в "
            "группу и писать команды не обязательно.\n"
            "\n"
            "Чтобы начать, добавьте меня в свою группу и выдайте права "
            "администратора. Нужные галочки уже отмечены в ссылке ниже."
        ),
        module="admin",
        description="Приветствие при первом запуске",
    ),
    TextDef(key="start_btn_add", default="Добавить в чат", module="admin",
            description="Кнопка: добавить бота в группу"),
    TextDef(key="start_btn_guide", default="Инструкция", module="admin",
            description="Кнопка: открыть инструкцию"),
    TextDef(key="start_btn_chats", default="Мои чаты", module="admin",
            description="Кнопка: список моих чатов"),
    TextDef(key="start_btn_profile", default="Профиль", module="admin",
            description="Кнопка: сведения обо мне"),
    TextDef(key="start_btn_home", default="В начало", module="admin",
            description="Кнопка: вернуться к приветствию"),
    # ─── Инструкция ──────────────────────────────────────────────────────────
    TextDef(
        key="guide_main",
        default=(
            "Что я умею\n"
            "\n"
            "Модерация. Блокировка, ограничение и предупреждения. Нарушителя "
            "можно указать ответом на сообщение, упоминанием или числовым "
            "идентификатором. После нескольких предупреждений наказание "
            "выдаётся само, порог вы задаёте.\n"
            "\n"
            "Антиспам. Семь правил: запрещённые слова, ссылки, частые "
            "сообщения, капс, массовые упоминания, вложения и пересылки. "
            "Каждое включается отдельно, для каждого своя мера.\n"
            "\n"
            "Пересылки. По умолчанию запрещены все, а разрешённые каналы вы "
            "добавляете в белый список. Так реклама не пролезет из канала, "
            "который вы ещё не видели.\n"
            "\n"
            "Встреча новичков. Приветствие с картинкой и кнопками, проверка "
            "на входе, защита от массового набега.\n"
            "\n"
            "Репутация и ранги. Участники благодарят друг друга, набирают "
            "очки и получают звания. Метрику и пороги настраиваете вы.\n"
            "\n"
            "Триггеры. Бот отвечает на ключевые слова тем, что вы ему "
            "покажете: текстом, картинкой, файлом.\n"
            "\n"
            "Статистика. Сводка по чату с графиком активности.\n"
            "\n"
            "Все тексты, которые вы видите, можно переписать под свой чат."
        ),
        module="admin",
        description="Инструкция: что умеет бот",
    ),
    TextDef(
        key="guide_commands",
        default=(
            "Команды\n"
            "\n"
            "Модерация, для модераторов и выше:\n"
            "/ban срок причина, блокировка\n"
            "/unban, снять блокировку\n"
            "/mute срок причина, запретить писать\n"
            "/unmute, разрешить писать\n"
            "/warn причина, предупреждение\n"
            "/unwarn, снять предупреждение\n"
            "/warns, сколько предупреждений\n"
            "\n"
            "Срок пишется как угодно: 30m, 2ч, 1d12h, 7д, навсегда. "
            "Число без единицы считается минутами.\n"
            "\n"
            "Для администраторов чата:\n"
            "/at ключ, создать триггер ответом на сообщение\n"
            "/dt ключ, удалить триггер\n"
            "/lt, список триггеров\n"
            "/sw, сделать приветствием сообщение, на которое отвечаете\n"
            "/aw слово, запретить слово\n"
            "/lw, список запрещённых слов\n"
            "/af, разрешить пересылки из канала, ответом на пересылку\n"
            "/lf, белый список источников\n"
            "/ar порог название, добавить ранг\n"
            "/raid on, включить защиту от набега вручную\n"
            "\n"
            "Для всех участников:\n"
            "/rep, репутация и место в чате\n"
            "/top, лучшие по репутации\n"
            "/rank, ваш ранг\n"
            "/st, сводка по чату"
        ),
        module="admin",
        description="Инструкция: список команд",
    ),
    TextDef(
        key="guide_setup",
        default=(
            "Как настроить\n"
            "\n"
            "1. Добавьте меня в группу кнопкой на первом экране.\n"
            "\n"
            "2. Выдайте права администратора. Обязательные: удаление "
            "сообщений и блокировка участников. Без них я не смогу ни "
            "убрать спам, ни остановить нарушителя.\n"
            "\n"
            "3. Вернитесь сюда и откройте Мои чаты. Ваша группа появится в "
            "списке.\n"
            "\n"
            "4. Выберите её и пройдите по разделам.\n"
            "\n"
            "Модули. Что работает в этом чате. Зелёная кнопка означает, что "
            "модуль включён, красная выключен.\n"
            "\n"
            "Настройки. Пороги, сроки и правила. Всё по разделам.\n"
            "\n"
            "Тексты. Любое моё сообщение можно переписать. Форматирование и "
            "премиум-эмодзи сохраняются.\n"
            "\n"
            "Содержимое. Приветствие, запрещённые слова и белый список "
            "пересылок.\n"
            "\n"
            "Настройки каждого чата независимы. Что включено в одном, не "
            "влияет на другой."
        ),
        module="admin",
        description="Инструкция: порядок настройки",
    ),
    TextDef(key="guide_btn_commands", default="Команды", module="admin",
            description="Кнопка: список команд"),
    TextDef(key="guide_btn_setup", default="Как настроить", module="admin",
            description="Кнопка: порядок настройки"),
    TextDef(key="guide_btn_back", default="К инструкции", module="admin",
            description="Кнопка: вернуться к инструкции"),
    # ─── Профиль ─────────────────────────────────────────────────────────────
    TextDef(
        key="profile_info",
        default=(
            "Ваш профиль\n"
            "\n"
            "Имя: {user}\n"
            "Идентификатор: {user_id}\n"
            "Статус: {role}\n"
            "Чатов под управлением: {count}\n"
            "\n"
            "{items}"
        ),
        module="admin",
        description="Сведения о человеке",
    ),
    TextDef(key="profile_role_owner", default="владелец бота", module="admin",
            description="Статус: владелец бота"),
    TextDef(key="profile_role_admin", default="администратор чата", module="admin",
            description="Статус: администратор чата"),
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
        "Отменить: /cancel",
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
        "Текущее значение в следующем сообщении.",
        module="admin",
        description="Экран одного текста",
    ),
    TextDef(
        key="admin_text_prompt",
        default=(
            "Пришлите новый текст для «{description}».\n\n"
            "Форматирование и премиум-эмодзи сохранятся. "
            "Плейсхолдеры подставятся при отправке.\n\nОтменить: /cancel"
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
        default="Приветствие настроено. Ниже показано, как его увидят новички.",
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
            "Плейсхолдеры подставятся при отправке.\n\nОтменить: /cancel"
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
            "Можно несколько, каждое с новой строки.\n\nОтменить: /cancel"
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
            "Отменить: /cancel"
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
