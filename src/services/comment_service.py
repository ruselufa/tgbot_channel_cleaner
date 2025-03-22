import logging
from datetime import datetime
from sqlalchemy.orm import Session
from src.models import Comment, MessageEdit, User

class CommentService:
    def __init__(self, session: Session):
        self.session = session
        self.logger = logging.getLogger(__name__)

    def get_comment(self, comment_id: int) -> Comment:
        """Получение комментария по ID"""
        return self.session.query(Comment).filter_by(id=comment_id).first()

    def create_comment(self, user_id: int, text: str, post_id: int, sentiment_score: float = None, toxicity_score: float = None) -> Comment:
        """Создание нового комментария"""
        try:
            comment = Comment(
                user_id=user_id,
                text=text,
                post_id=post_id,
                sentiment_score=sentiment_score,
                toxicity_score=toxicity_score
            )
            self.session.add(comment)
            self.session.commit()
            return comment
        except Exception as e:
            self.logger.error(f"Error creating comment: {e}")
            self.session.rollback()
            raise

    def approve_comment(self, comment: Comment, moderator_id: int) -> None:
        """Одобрение комментария"""
        try:
            comment.is_approved = True
            comment.is_rejected = False
            comment.updated_at = datetime.utcnow()
            self.session.commit()
            self.logger.info(f"Comment {comment.id} approved by moderator {moderator_id}")
        except Exception as e:
            self.logger.error(f"Error approving comment: {e}")
            self.session.rollback()
            raise

    def reject_comment(self, comment: Comment, moderator_id: int, reason: str = None) -> None:
        """Отклонение комментария"""
        try:
            comment.is_approved = False
            comment.is_rejected = True
            comment.updated_at = datetime.utcnow()
            self.session.commit()
            self.logger.info(f"Comment {comment.id} rejected by moderator {moderator_id}. Reason: {reason}")
        except Exception as e:
            self.logger.error(f"Error rejecting comment: {e}")
            self.session.rollback()
            raise

    def record_edit(self, comment: Comment, new_text: str, sentiment_change: float = None, is_suspicious: bool = False) -> MessageEdit:
        """Запись изменения комментария"""
        try:
            edit = MessageEdit(
                comment_id=comment.id,
                old_text=comment.text,
                new_text=new_text,
                sentiment_change=sentiment_change,
                is_suspicious=is_suspicious
            )
            self.session.add(edit)
            
            # Обновляем текст комментария
            comment.text = new_text
            comment.updated_at = datetime.utcnow()
            
            self.session.commit()
            return edit
        except Exception as e:
            self.logger.error(f"Error recording edit: {e}")
            self.session.rollback()
            raise

    def get_user_comments(self, user_id: int, limit: int = 10) -> list[Comment]:
        """Получение комментариев пользователя"""
        try:
            return self.session.query(Comment)\
                .filter_by(user_id=user_id)\
                .order_by(Comment.created_at.desc())\
                .limit(limit)\
                .all()
        except Exception as e:
            self.logger.error(f"Error getting user comments: {e}")
            return []

    def get_pending_comments(self, limit: int = 10) -> list[Comment]:
        """Получение комментариев на модерации"""
        try:
            return self.session.query(Comment)\
                .filter_by(is_approved=False, is_rejected=False)\
                .order_by(Comment.created_at.asc())\
                .limit(limit)\
                .all()
        except Exception as e:
            self.logger.error(f"Error getting pending comments: {e}")
            return []

    def get_suspicious_edits(self, limit: int = 10) -> list[MessageEdit]:
        """Получение подозрительных изменений"""
        try:
            return self.session.query(MessageEdit)\
                .filter_by(is_suspicious=True)\
                .order_by(MessageEdit.created_at.desc())\
                .limit(limit)\
                .all()
        except Exception as e:
            self.logger.error(f"Error getting suspicious edits: {e}")
            return [] 