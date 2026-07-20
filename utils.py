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
    return data.get("operators", [])

def save_operators(operators: list):
    data = load_links()
    data["operators"] = operators
    save_links(data)

def format_user_message(user_id: int, username: str, first_name: str, text: str) -> str:
    """Форматирует сообщение для отправки операторам/админам (коротко и красиво)"""
    now = datetime.now().strftime("%d.%m %H:%M")
    name = first_name or username or str(user_id)
    return (
        f"📩 <b>Новое обращение</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"👤 {name}\n"
        f"🆔 <code>{user_id}</code>\n"
        f"🕐 {now}\n"
        f"━━━━━━━━━━━━━━\n\n"
        f"{text}\n\n"
        f"━━━━━━━━━━━━━━\n"
        f"<i>Ответьте реплаем</i>"
    )