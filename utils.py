import json
import os
from datetime import datetime

LINKS_FILE = "link.json"

def ensure_link_json():
    """Создает link.json если файл не существует"""
    if not os.path.exists(LINKS_FILE):
        default_data = {
            "links": {
                "chat": "",
                "news": "",
                "reserve": "",
                "bot": "",
                "website": "",
                "ceo": "",
                "operator": ""
            },
            "operators": []
        }
        with open(LINKS_FILE, "w", encoding="utf-8") as f:
            json.dump(default_data, f, indent=4, ensure_ascii=False)

def load_links():
    """Загружает данные из link.json"""
    with open(LINKS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_links(data):
    """Сохраняет данные в link.json"""
    with open(LINKS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def get_link(key: str) -> str:
    """Получает ссылку по ключу"""
    data = load_links()
    return data["links"].get(key, "")

def get_operators() -> list:
    """Получает список операторов"""
    data = load_links()
    return data.get("operators", [])

def save_operators(operators: list):
    """Сохраняет список операторов"""
    data = load_links()
    data["operators"] = operators
    save_links(data)

def format_user_message(user_id: int, username: str, first_name: str, text: str) -> str:
    """Форматирует сообщение для отправки операторам/админам"""
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    return (
        f"📨 Новое обращение\n\n"
        f"👤 Пользователь\n{first_name or 'Не указан'}\n\n"
        f"🆔 ID\n{user_id}\n\n"
        f"📅 Дата\n{now}\n\n"
        f"━━━━━━━━━━━━━━\n\n"
        f"{text}\n\n"
        f"━━━━━━━━━━━━━━\n\n"
        f"Ответьте реплаем."
    )

def format_stats(total: int, sent: int, failed: int, blocked: int, errors: int) -> str:
    """Форматирует статистику рассылки"""
    return (
        f"📨 Рассылка завершена\n\n"
        f"👥 Всего пользователей: {total}\n"
        f"✅ Отправлено: {sent}\n"
        f"🚫 Заблокировали бота: {blocked}\n"
        f"❌ Ошибок: {errors}"
    )