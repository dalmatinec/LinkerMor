import logging
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from config import ADMIN_IDS
from database import get_user_count, get_active_user_count, get_blocked_user_count
from utils import load_links, save_links, get_operators, save_operators, get_link, set_chat_id
from keyboards import admin_panel, main_menu, cancel_inline
from states import EditLinkStates, EditOperatorsStates

logger = logging.getLogger(__name__)
router = Router()

# Проверка на админа
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

# ============ ОБРАБОТЧИКИ ИНЛАЙН-КНОПОК АДМИНКИ ============
@router.callback_query(F.data == "admin_stats")
async def admin_stats_callback(callback: CallbackQuery):
    """Статистика (инлайн)"""
    await callback.answer()
    if not is_admin(callback.from_user.id):
        return

    total = get_user_count()
    active = get_active_user_count()
    blocked = get_blocked_user_count()

    await callback.message.answer(
        f"📊 Статистика\n\n"
        f"👥 Всего пользователей: {total}\n"
        f"✅ Активных: {active}\n"
        f"🚫 Заблокировали бота: {blocked}"
    )

@router.callback_query(F.data == "admin_edit_links")
async def admin_edit_links_callback(callback: CallbackQuery, state: FSMContext):
    """Изменение ссылок (инлайн)"""
    await callback.answer()
    if not is_admin(callback.from_user.id):
        return
    await admin_edit_links(callback.message, state)

@router.callback_query(F.data == "admin_edit_operators")
async def admin_edit_operators_callback(callback: CallbackQuery, state: FSMContext):
    """Изменение операторов (инлайн)"""
    await callback.answer()
    if not is_admin(callback.from_user.id):
        return
    await admin_edit_operators(callback.message, state)

@router.callback_query(F.data == "admin_back_to_menu")
async def admin_back_to_menu_callback(callback: CallbackQuery):
    """Назад в меню (инлайн)"""
    await callback.answer()
    if not is_admin(callback.from_user.id):
        return
    await callback.message.answer(
        "Возврат в главное меню",
        reply_markup=main_menu()
    )

# ============ ФУНКЦИИ ДЛЯ РАБОТЫ С ССЫЛКАМИ ============
async def admin_edit_links(message: types.Message, state: FSMContext):
    """Начало изменения ссылок"""
    data = load_links()
    links = data.get("links", {})

    link_list = "\n".join([f"• {key}: {value or 'не указана'}" for key, value in links.items()])

    # Инлайн-кнопки для выбора ссылки
    buttons = []
    for key in links.keys():
        buttons.append([InlineKeyboardButton(text=key, callback_data=f"edit_link_{key}")])
    buttons.append([InlineKeyboardButton(text="◀️ Отмена", callback_data="cancel_edit_links")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await state.set_state(EditLinkStates.choosing_link)
    await message.answer(
        f"🔗 Выберите ссылку для изменения:\n\n{link_list}",
        reply_markup=keyboard
    )

@router.callback_query(F.data.startswith("edit_link_"))
async def process_link_choice(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора ссылки (инлайн)"""
    await callback.answer()
    if not is_admin(callback.from_user.id):
        return

    link_key = callback.data.replace("edit_link_", "")

    data = load_links()
    links = data.get("links", {})

    if link_key not in links:
        await callback.message.answer("❌ Неверный выбор. Попробуйте снова.")
        return

    await state.update_data(selected_link=link_key)
    await state.set_state(EditLinkStates.entering_value)
    await callback.message.answer(
        f"Введите новое значение для ссылки: {link_key}\n"
        f"Текущее: {links[link_key] or 'не указана'}",
        reply_markup=cancel_inline()
    )

@router.callback_query(F.data == "cancel_edit_links")
async def cancel_edit_links(callback: CallbackQuery, state: FSMContext):
    """Отмена изменения ссылок"""
    await callback.answer()
    await state.clear()
    await callback.message.answer(
        "❌ Действие отменено\n\n"
        "Выйти в главное меню - /start\n"
        "Войти в админ панель - /admin"
    )

@router.message(EditLinkStates.entering_value)
async def process_link_value(message: types.Message, state: FSMContext):
    """Обработка ввода нового значения ссылки"""
    if not is_admin(message.from_user.id):
        return

    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer(
            "❌ Действие отменено\n\n"
            "Выйти в главное меню - /start\n"
            "Войти в админ панель - /admin"
        )
        return

    data = load_links()
    selected = await state.get_data()
    link_key = selected.get("selected_link")

    if not link_key:
        await state.clear()
        await message.answer(
            "❌ Действие отменено\n\n"
            "Выйти в главное меню - /start\n"
            "Войти в админ панель - /admin"
        )
        return

    data["links"][link_key] = message.text
    save_links(data)

    await state.clear()
    await message.answer(
        f"✅ Ссылка обновлена!\n\n"
        f"{link_key}: {message.text}",
        reply_markup=admin_panel()
    )

# ============ ФУНКЦИИ ДЛЯ РАБОТЫ С ОПЕРАТОРАМИ ============
async def admin_edit_operators(message: types.Message, state: FSMContext):
    """Начало изменения операторов"""
    operators = get_operators()
    operator_list = "\n".join([f"• {op}" for op in operators]) if operators else "Список пуст"

    await state.set_state(EditOperatorsStates.entering_operator)
    await message.answer(
        f"👨‍💻 Управление операторами\n\n"
        f"Текущие операторы:\n{operator_list}\n\n"
        f"Введите Telegram ID оператора для добавления\n"
        f"или отправьте 0 для удаления оператора.",
        reply_markup=cancel_inline()
    )

@router.message(EditOperatorsStates.entering_operator)
async def process_operator_input(message: types.Message, state: FSMContext):
    """Обработка ввода ID оператора"""
    if not is_admin(message.from_user.id):
        return

    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer(
            "❌ Действие отменено\n\n"
            "Выйти в главное меню - /start\n"
            "Войти в админ панель - /admin"
        )
        return

    try:
        operator_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Введите корректный числовой ID")
        return

    operators = get_operators()

    if operator_id == 0:
        if not operators:
            await message.answer("❌ Список операторов пуст")
            return

        # Инлайн-кнопки для выбора оператора на удаление
        buttons = []
        for op in operators:
            buttons.append([InlineKeyboardButton(text=str(op), callback_data=f"delete_operator_{op}")])
        buttons.append([InlineKeyboardButton(text="◀️ Отмена", callback_data="cancel_delete_operator")])

        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

        await state.update_data(mode="delete")
        await state.set_state(EditOperatorsStates.entering_operator)
        await message.answer(
            f"Выберите оператора для удаления:\n\n"
            f"{chr(10).join([f'• {op}' for op in operators])}",
            reply_markup=keyboard
        )
        return

    if operator_id in operators:
        await message.answer(f"❌ Оператор с ID {operator_id} уже существует")
        return

    operators.append(operator_id)
    save_operators(operators)

    await state.clear()
    await message.answer(
        f"✅ Оператор добавлен!\n\n"
        f"Текущие операторы:\n{chr(10).join([f'• {op}' for op in operators])}",
        reply_markup=admin_panel()
    )

@router.callback_query(F.data.startswith("delete_operator_"))
async def process_operator_delete_callback(callback: CallbackQuery, state: FSMContext):
    """Удаление оператора (инлайн)"""
    await callback.answer()
    if not is_admin(callback.from_user.id):
        return

    operator_id = int(callback.data.replace("delete_operator_", ""))

    operators = get_operators()

    if operator_id not in operators:
        await callback.message.answer(f"❌ Оператор с ID {operator_id} не найден")
        return

    operators.remove(operator_id)
    save_operators(operators)

    await state.clear()
    await callback.message.answer(
        f"✅ Оператор удален!\n\n"
        f"Текущие операторы:\n{chr(10).join([f'• {op}' for op in operators]) if operators else 'Список пуст'}",
        reply_markup=admin_panel()
    )

@router.callback_query(F.data == "cancel_delete_operator")
async def cancel_delete_operator(callback: CallbackQuery, state: FSMContext):
    """Отмена удаления оператора"""
    await callback.answer()
    await state.clear()
    await callback.message.answer(
        "❌ Действие отменено\n\n"
        "Выйти в главное меню - /start\n"
        "Войти в админ панель - /admin"
    )

# ============ КОМАНДЫ ============
@router.message(Command("admin"), F.chat.type == "private")
async def cmd_admin(message: types.Message):
    """Команда /admin - открыть админ-панель (только в ЛС)"""
    if not is_admin(message.from_user.id):
        return

    await message.answer(
        "👋 Добро пожаловать в админ-панель!\n\n"
        "Выберите действие:",
        reply_markup=admin_panel()
    )

@router.message(Command("set_chat"), F.chat.type == "private")
async def cmd_set_chat(message: types.Message):
    """Привязать чат по ID (только в ЛС)"""
    if not is_admin(message.from_user.id):
        return

    args = message.text.split()
    if len(args) < 2:
        await message.answer("❌ Используйте: /set_chat ID_чата")
        return

    try:
        chat_id = int(args[1])
        set_chat_id("chat", chat_id)
        await message.answer(f"✅ Чат добавлен (ID: {chat_id})")
    except ValueError:
        await message.answer("❌ ID должен быть числом")

@router.message(Command("set_news"), F.chat.type == "private")
async def cmd_set_news(message: types.Message):
    """Привязать канал по ID (только в ЛС)"""
    if not is_admin(message.from_user.id):
        return

    args = message.text.split()
    if len(args) < 2:
        await message.answer("❌ Используйте: /set_news ID_канала")
        return

    try:
        chat_id = int(args[1])
        set_chat_id("news", chat_id)
        await message.answer(f"✅ Канал добавлен (ID: {chat_id})")
    except ValueError:
        await message.answer("❌ ID должен быть числом")

@router.message(Command("set_res"), F.chat.type == "private")
async def cmd_set_res(message: types.Message):
    """Привязать резервный чат по ID (только в ЛС)"""
    if not is_admin(message.from_user.id):
        return

    args = message.text.split()
    if len(args) < 2:
        await message.answer("❌ Используйте: /set_res ID_чата")
        return

    try:
        chat_id = int(args[1])
        set_chat_id("reserve", chat_id)
        await message.answer(f"✅ Резерв добавлен (ID: {chat_id})")
    except ValueError:
        await message.answer("❌ ID должен быть числом")

@router.message(Command("help"), F.chat.type == "private")
async def cmd_help(message: types.Message):
    """Команда /help - помощь для админов (только в ЛС)"""
    if not is_admin(message.from_user.id):
        return

    await message.answer(
        "🤖 Команды администратора:\n\n"
        "/stats - Статистика пользователей\n"
        "/send - Рассылка (ответьте на сообщение)\n"
        "/forward - Пересылка (ответьте на сообщение)\n"
        "/set_chat ID - Привязать чат\n"
        "/set_news ID - Привязать канал\n"
        "/set_res ID - Привязать резервный чат\n"
        "/help - Эта справка"
    )