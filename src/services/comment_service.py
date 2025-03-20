from datetime import datetime
from sqlalchemy.orm import Session
from models import Comment, MessageEdit, User

class CommentService:
    def __init__(self, session: Session):
        self.session = session

    def create_comment(self, user: User, post_id: int, text: str, sentiment_score: float) -> Comment:
        comment = Comment(
            user_id=user.id,
            post_id=post_id,
            text=text,
            sentiment_score=sentiment_score,
            status='pending'
        )
        self.session.add(comment)
        self.session.commit()
        return comment

    def approve_comment(self, comment: Comment, moderator_id: int):
        comment.status = 'approved'
        comment.moderated_by = moderator_id
        comment.moderated_at = datetime.utcnow()
        self.session.commit()

    def reject_comment(self, comment: Comment, moderator_id: int, reason: str):
        comment.status = 'rejected'
        comment.moderated_by = moderator_id
        comment.rejection_reason = reason
        comment.moderated_at = datetime.utcnow()
        self.session.commit()
        
    def record_edit(self, comment: Comment, new_text: str, 
                   sentiment_change: float, is_suspicious: bool,
                   analysis_data: dict) -> MessageEdit:
        """Запись изменения сообщения"""
        comment.is_edited = True
        comment.edit_count += 1
        comment.last_edit_at = datetime.utcnow()
        
        edit = MessageEdit(
            user_id=comment.user_id,
            comment_id=comment.id,
            old_text=comment.text,
            new_text=new_text,
            sentiment_change=sentiment_change,
            is_suspicious=is_suspicious,
            analysis_data=analysis_data
        )
        
        self.session.add(edit)
        comment.text = new_text
        self.session.commit()
        
        return edit 