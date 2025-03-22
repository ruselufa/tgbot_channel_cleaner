from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import os

from config.settings import DATABASE_URL

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

# Создаем базовый класс для моделей
Base = declarative_base()

# Создаем подключение к базе данных
engine = create_engine(DATABASE_URL)

# Создаем фабрику сессий
Session = sessionmaker(bind=engine)

# Создаем все таблицы
Base.metadata.create_all(engine) 