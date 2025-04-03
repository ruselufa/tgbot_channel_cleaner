import psycopg2
from dotenv import load_dotenv
import os
import time
from config.settings import DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME, DB_SSL_MODE

def test_connection():
    print(f"Попытка подключения к базе данных: {DB_HOST}:{DB_PORT}/{DB_NAME}")
    
    for attempt in range(3):
        try:
            conn = psycopg2.connect(
                dbname=DB_NAME,
                user=DB_USER,
                password=DB_PASSWORD,
                host=DB_HOST,
                port=DB_PORT,
                sslmode=DB_SSL_MODE
            )
            print("Подключение успешно!")
            
            cur = conn.cursor()
            cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
            tables = cur.fetchall()
            print("\nСуществующие таблицы:")
            for table in tables:
                print(f"- {table[0]}")
            
            cur.close()
            conn.close()
            return True
            
        except Exception as e:
            print(f"Попытка {attempt + 1} не удалась: {str(e)}")
            if attempt < 2:
                print("Ожидание 5 секунд перед следующей попыткой...")
                time.sleep(5)
    
    return False

if __name__ == "__main__":
    if test_connection():
        print("\nТест подключения успешно завершен!")
    else:
        print("\nНе удалось подключиться к базе данных после всех попыток.") 