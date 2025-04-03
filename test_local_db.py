import psycopg2
import time

def test_connection():
    print("Попытка подключения к базе данных через localhost...")
    
    for attempt in range(3):
        try:
            conn = psycopg2.connect(
                dbname="tgbot_moderator",
                user="postgres",
                password="postgres",
                host="localhost",
                port="5432"
            )
            print("Подключение успешно!")
            
            cur = conn.cursor()
            cur.execute("SELECT 1")
            result = cur.fetchone()
            print(f"Результат запроса: {result}")
            
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