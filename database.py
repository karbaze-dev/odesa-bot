import sqlite3

DB_NAME = "odesa_concierge.db"

def init_db():
    """Инициализация базы данных и создание таблиц"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # 1. Таблица пользователей
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            full_name TEXT,
            username TEXT,
            phone TEXT,
            registered_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 2. Таблица категорий мест (Еда, Культура, Развлечения и т.д.)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            category_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE
        )
    """)

    # 3. Таблица мест/заведений в Одессе
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS venues (
            venue_id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER,
            name TEXT,
            description TEXT,
            latitude REAL,
            longitude REAL,
            FOREIGN KEY (category_id) REFERENCES categories(category_id)
        )
    """)

    # 4. Таблица событий и мероприятий
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            description TEXT,
            event_date TEXT,
            venue_id INTEGER,
            FOREIGN KEY (venue_id) REFERENCES venues(venue_id)
        )
    """)

    # 5. Таблица поездок (для истории и аналитики)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trips (
            trip_id TEXT PRIMARY KEY,
            passenger_id INTEGER,
            status TEXT DEFAULT 'active',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            completed_at TEXT,
            fare REAL DEFAULT 0.0,
            FOREIGN KEY (passenger_id) REFERENCES users(telegram_id)
        )
    """)

    conn.commit()
    conn.close()
    print("База данных успешно создана и инициализирована!")

if __name__ == "__main__":
    init_db()