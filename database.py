import sqlite3
from datetime import datetime
from config import DB_NAME

def get_connection():
    return sqlite3.connect(DB_NAME)

def init_db():
    with get_connection() as conn:
        cursor = conn.cursor()
        # Таблица пользователей
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
        
        # Проверяем существование старой таблицы user_links
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user_links'")
        table_exists = cursor.fetchone()
        
        if table_exists:
            # Проверяем структуру текущей таблицы
            cursor.execute("PRAGMA table_info(user_links)")
            columns = [col[1] for col in cursor.fetchall()]
            
            # Если старая структура (user_id PRIMARY KEY) - пересоздаём
            if 'user_id' in columns and 'link_type' in columns and 'created_at' in columns:
                # Проверяем, есть ли PRIMARY KEY на user_id
                cursor.execute("PRAGMA index_list('user_links')")
                indexes = cursor.fetchall()
                
                # Переименовываем старую таблицу
                cursor.execute("ALTER TABLE user_links RENAME TO user_links_old")
                
                # Создаём новую таблицу с составным ключом
                cursor.execute("""
                    CREATE TABLE user_links (
                        user_id INTEGER,
                        link_type TEXT,
                        created_at INTEGER,
                        PRIMARY KEY (user_id, link_type)
                    )
                """)
                
                # Переносим данные
                cursor.execute("""
                    INSERT INTO user_links (user_id, link_type, created_at)
                    SELECT user_id, link_type, created_at FROM user_links_old
                """)
                
                # Удаляем старую таблицу
                cursor.execute("DROP TABLE user_links_old")
        else:
            # Создаём новую таблицу с составным ключом
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_links (
                    user_id INTEGER,
                    link_type TEXT,
                    created_at INTEGER,
                    PRIMARY KEY (user_id, link_type)
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

def get_user_link(user_id: int, link_type: str):
    """Получить активную ссылку пользователя по типу"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT created_at FROM user_links WHERE user_id = ? AND link_type = ?",
            (user_id, link_type)
        )
        result = cursor.fetchone()
        return result[0] if result else None

def save_user_link(user_id: int, link_type: str, created_at: int):
    """Сохранить ссылку пользователя"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO user_links (user_id, link_type, created_at) VALUES (?, ?, ?)",
            (user_id, link_type, created_at)
        )
        conn.commit()

def delete_user_link(user_id: int, link_type: str):
    """Удалить ссылку пользователя по типу"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM user_links WHERE user_id = ? AND link_type = ?",
            (user_id, link_type)
        )
        conn.commit()