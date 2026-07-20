import json
import os
from datetime import datetime

LINKS_FILE = "link.json"

def ensure_link_json():
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
    with open(LINKS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_links(data):
    with open(LINKS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def get_link(key: str) -> str:
    data = load_links()
    return data["links"].get(key, "")

def get_operators() -> list:
    data = load_links()
    print("LINK.JSON =", os.path.abspath(LINKS_FILE))
    print("OPERATORS =", data.get("operators", []))
    return data.get("operators", [])

def save_operators(operators: list):
    data = load_links()
    data["operators"] = operators
    save_links(data)

def format_user_message(user_id: int, username: str, first_name: str, text: str) -> str:
    """Форматирует сообщение для отправки операторам/админам"""
    now = datetime.now().strftime("%d.%m %H:%M")

    name = first_name or "Не указан"
    username_line = f"Юзер: @{username}" if username else "Юзер: нет"

    return (
        f"<b>📨 Новое обращение</b>\n\n"
        f"💬 <b>Сообщение:</b>\n"
        f"{text}\n\n"
        f"───────────────\n"
        f"👤 Имя: {name}\n"
        f"🕊 {username_line}\n"
        f"🆔 ID: {user_id}\n"
        f"🕒 {now}\n\n"
        f"↩ Ответьте реплаем."
    )