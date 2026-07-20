import sqlite3
from datetime import datetime
from config import DB_NAME

def get_connection():
    return sqlite3.connect(DB_NAME)

def init_db():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                first_name TEXT,
                join_date TEXT,
                is_blocked INTEGER DEFAULT 0
            )
        """)
        conn.commit()

def add_user(telegram_id: int, username: str = None, first_name: str = None):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR IGNORE INTO users (telegram_id, username, first_name, join_date) VALUES (?, ?, ?, ?)",
            (telegram_id, username, first_name, datetime.now().isoformat())
        )
        conn.commit()

def get_all_users():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT telegram_id, is_blocked FROM users")
        return cursor.fetchall()

def get_user_count():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        return cursor.fetchone()[0]

def get_active_user_count():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users WHERE is_blocked = 0")
        return cursor.fetchone()[0]

def get_blocked_user_count():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users WHERE is_blocked = 1")
        return cursor.fetchone()[0]

def mark_user_blocked(telegram_id: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_blocked = 1 WHERE telegram_id = ?", (telegram_id,))
        conn.commit()