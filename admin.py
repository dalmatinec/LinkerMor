import logging
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

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

# Фильтр для админ-панели
@router.message(F.text == "◀️ Назад в меню")
async def back_to_menu(message: types.Message):
    """Возврат в главное меню"""
    if not is_admin(message.from_user.id):
        return
    await message.answer(
        "Возврат в главное меню",
        reply_markup=main_menu()
    )

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

@router.message(F.text == "📊 Статистика")
async def admin_stats(message: types.Message):
    """Статистика в админ-панели"""
    if not is_admin(message.from_user.id):
        return

    total = get_user_count()
    active = get_active_user_count()
    blocked = get_blocked_user_count()

    await message.answer(
        f"📊 Статистика\n\n"
        f"👥 Всего пользователей: {total}\n"
        f"✅ Активных: {active}\n"
        f"🚫 Заблокировали бота: {blocked}"
    )

@router.message(F.text == "🔗 Изменить ссылки")
async def admin_edit_links(message: types.Message, state: FSMContext):
    """Начало изменения ссылок"""
    if not is_admin(message.from_user.id):
        return

    data = load_links()
    links = data.get("links", {})

    # Формируем список ссылок
    link_list = "\n".join([f"• {key}: {value or 'не указана'}" for key, value in links.items()])

    # Создаем клавиатуру со ссылками
    buttons = []
    for key in links.keys():
        buttons.append([KeyboardButton(text=key)])
    buttons.append([KeyboardButton(text="◀️ Отмена")])

    keyboard = ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

    await state.set_state(EditLinkStates.choosing_link)
    await message.answer(
        f"🔗 Выберите ссылку для изменения:\n\n{link_list}",
        reply_markup=keyboard
    )

@router.message(EditLinkStates.choosing_link)
async def process_link_choice(message: types.Message, state: FSMContext):
    """Обработка выбора ссылки"""
    if not is_admin(message.from_user.id):
        return

    if message.text == "◀️ Отмена":
        await state.clear()
        await message.answer(
            "❌ Отменено",
            reply_markup=admin_panel()
        )
        return

    data = load_links()
    links = data.get("links", {})

    if message.text not in links:
        await message.answer("❌ Неверный выбор. Попробуте снова.")
        return

    await state.update_data(selected_link=message.text)
    await state.set_state(EditLinkStates.entering_value)
    await message.answer(
        f"Введите новое значение для ссылки: {message.text}\n"
        f"Текущее: {links[message.text] or 'не указана'}",
        reply_markup=cancel_inline()
    )

@router.message(EditLinkStates.entering_value)
async def process_link_value(message: types.Message, state: FSMContext):
    """Обработка ввода нового значения ссылки"""
    if not is_admin(message.from_user.id):
        return

    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer(
            "❌ Отменено",
            reply_markup=admin_panel()
        )
        return

    data = load_links()
    selected = await state.get_data()
    link_key = selected.get("selected_link")

    if not link_key:
        await state.clear()
        await message.answer("❌ Ошибка. Попробуйте снова.", reply_markup=admin_panel())
        return

    # Сохраняем новое значение
    data["links"][link_key] = message.text
    save_links(data)

    await state.clear()
    await message.answer(
        f"✅ Ссылка обновлена!\n\n"
        f"{link_key}: {message.text}",
        reply_markup=admin_panel()
    )

@router.message(F.text == "👨‍💻 Изменить операторов")
async def admin_edit_operators(message: types.Message, state: FSMContext):
    """Начало изменения операторов"""
    if not is_admin(message.from_user.id):
        return

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
            "❌ Отменено",
            reply_markup=admin_panel()
        )
        return

    try:
        operator_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Введите корректный числовой ID")
        return

    operators = get_operators()

    if operator_id == 0:
        # Режим удаления
        if not operators:
            await message.answer("❌ Список операторов пуст")
            return

        # Создаем клавиатуру для выбора оператора на удаление
        buttons = []
        for op in operators:
            buttons.append([KeyboardButton(text=str(op))])
        buttons.append([KeyboardButton(text="◀️ Отмена")])

        keyboard = ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

        await state.update_data(mode="delete")
        await state.set_state(EditOperatorsStates.entering_operator)
        await message.answer(
            f"Выберите оператора для удаления:\n\n"
            f"{chr(10).join([f'• {op}' for op in operators])}",
            reply_markup=keyboard
        )
        return

    # Режим добавления
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

# Обработка выбора оператора для удаления
@router.message(EditOperatorsStates.entering_operator)
async def process_operator_delete(message: types.Message, state: FSMContext):
    """Обработка удаления оператора"""
    if not is_admin(message.from_user.id):
        return

    if message.text == "◀️ Отмена":
        await state.clear()
        await message.answer(
            "❌ Отменено",
            reply_markup=admin_panel()
        )
        return

    data = await state.get_data()
    mode = data.get("mode")

    if mode == "delete":
        try:
            operator_id = int(message.text.strip())
        except ValueError:
            await message.answer("❌ Введите корректный ID")
            return

        operators = get_operators()

        if operator_id not in operators:
            await message.answer(f"❌ Оператор с ID {operator_id} не найден")
            return

        operators.remove(operator_id)
        save_operators(operators)

        await state.clear()
        await message.answer(
            f"✅ Оператор удален!\n\n"
            f"Текущие операторы:\n{chr(10).join([f'• {op}' for op in operators]) if operators else 'Список пуст'}",
            reply_markup=admin_panel()
        )