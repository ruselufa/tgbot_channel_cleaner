import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError
from dotenv import load_dotenv
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config.settings import DATABASE_URL
from src.models import Base, User, Comment, MessageEdit, Warning

logger = logging.getLogger(__name__)

def init_db():
    """Инициализация базы данных"""
    try:
        # Создаем подключение к базе данных
        engine = create_engine(DATABASE_URL)
        
        # Создаем все таблицы
        Base.metadata.create_all(engine)
        
        # Создаем фабрику сессий
        Session = sessionmaker(bind=engine)
        
        logger.info("Database initialized successfully")
        return Session
        
    except SQLAlchemyError as e:
        logger.error(f"Error initializing database: {e}")
        raise

if __name__ == "__main__":
    print("Initializing database...")
    init_db()
    print("Database initialized successfully!") 