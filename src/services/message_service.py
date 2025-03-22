import logging
from datetime import datetime
from sqlalchemy.orm import Session
from src.models import Comment

class MessageService:
    def __init__(self, session: Session = None):
        self.session = session
        self.logger = logging.getLogger(__name__)

    def save_message(self, user_id: int, text: str, post_id: int, sentiment_score: float = None, toxicity_score: float = None) -> Comment:
        """Сохранение сообщения в базу данных"""
        try:
            message = Comment(
                user_id=user_id,
                text=text,
                post_id=post_id,
                sentiment_score=sentiment_score,
                toxicity_score=toxicity_score,
                created_at=datetime.utcnow()
            )
            if self.session:
                self.session.add(message)
                self.session.commit()
            return message
        except Exception as e:
            self.logger.error(f"Error saving message: {e}")
            if self.session:
                self.session.rollback()
            raise

    def get_message(self, message_id: int) -> Comment:
        """Получение сообщения по ID"""
        try:
            if not self.session:
                return None
            return self.session.query(Comment).filter_by(id=message_id).first()
        except Exception as e:
            self.logger.error(f"Error getting message: {e}")
            return None

    def update_message(self, message_id: int, new_text: str) -> bool:
        """Обновление текста сообщения"""
        try:
            if not self.session:
                return False
            message = self.session.query(Comment).filter_by(id=message_id).first()
            if message:
                message.text = new_text
                message.updated_at = datetime.utcnow()
                self.session.commit()
                return True
            return False
        except Exception as e:
            self.logger.error(f"Error updating message: {e}")
            self.session.rollback()
            return False

    def delete_message(self, message_id: int) -> bool:
        """Удаление сообщения"""
        try:
            if not self.session:
                return False
            message = self.session.query(Comment).filter_by(id=message_id).first()
            if message:
                self.session.delete(message)
                self.session.commit()
                return True
            return False
        except Exception as e:
            self.logger.error(f"Error deleting message: {e}")
            self.session.rollback()
            return False

    def get_user_messages(self, user_id: int, limit: int = 100) -> list[Comment]:
        """Получение последних сообщений пользователя"""
        try:
            if not self.session:
                return []
            return self.session.query(Comment)\
                .filter_by(user_id=user_id)\
                .order_by(Comment.created_at.desc())\
                .limit(limit)\
                .all()
        except Exception as e:
            self.logger.error(f"Error getting user messages: {e}")
            return []

    def get_negative_messages(self, limit: int = 100) -> list[Comment]:
        """Получение последних негативных сообщений"""
        try:
            if not self.session:
                return []
            return self.session.query(Comment)\
                .filter_by(is_rejected=True)\
                .order_by(Comment.created_at.desc())\
                .limit(limit)\
                .all()
        except Exception as e:
            self.logger.error(f"Error getting negative messages: {e}")
            return [] 