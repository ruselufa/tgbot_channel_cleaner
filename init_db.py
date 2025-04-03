import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from config.settings import DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME, DB_SSL_MODE

def init_database():
    # Подключаемся к postgres по умолчанию
    conn = psycopg2.connect(
        dbname="postgres",
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT,
        sslmode=DB_SSL_MODE
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()

    try:
        # Создаем базу данных, если она не существует
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DB_NAME,))
        exists = cur.fetchone()
        
        if not exists:
            print(f"Создание базы данных {DB_NAME}...")
            cur.execute(f'CREATE DATABASE {DB_NAME}')
            print("База данных создана успешно!")
        else:
            print(f"База данных {DB_NAME} уже существует.")

        # Подключаемся к новой базе данных
        cur.close()
        conn.close()
        
        conn = psycopg2.connect(
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT,
            sslmode=DB_SSL_MODE
        )
        cur = conn.cursor()

        # Создаем таблицы
        print("\nСоздание таблиц...")
        
        # Таблица bans
        cur.execute("""
            CREATE TABLE IF NOT EXISTS bans (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                chat_id BIGINT NOT NULL,
                reason TEXT,
                banned_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                banned_until TIMESTAMP WITH TIME ZONE,
                UNIQUE(user_id, chat_id)
            )
        """)
        
        # Таблица blacklist
        cur.execute("""
            CREATE TABLE IF NOT EXISTS blacklist (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                chat_id BIGINT NOT NULL,
                reason TEXT,
                added_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, chat_id)
            )
        """)
        
        # Таблица moderation_stats
        cur.execute("""
            CREATE TABLE IF NOT EXISTS moderation_stats (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                chat_id BIGINT NOT NULL,
                message_count INTEGER DEFAULT 0,
                warning_count INTEGER DEFAULT 0,
                last_warning_at TIMESTAMP WITH TIME ZONE,
                last_message_at TIMESTAMP WITH TIME ZONE,
                UNIQUE(user_id, chat_id)
            )
        """)
        
        # Таблица warnings
        cur.execute("""
            CREATE TABLE IF NOT EXISTS warnings (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                chat_id BIGINT NOT NULL,
                reason TEXT,
                warned_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                warned_by BIGINT NOT NULL
            )
        """)
        
        conn.commit()
        print("Таблицы созданы успешно!")
        
    except Exception as e:
        print(f"Ошибка: {str(e)}")
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    print("Начало инициализации базы данных...")
    init_database()
    print("Инициализация завершена!") 