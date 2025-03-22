from datetime import datetime
from sqlalchemy.orm import Session
from src.models import ModeratorLog, User, Comment

class ModeratorLogService:
    def __init__(self, session: Session):
        self.session = session

    def log_action(self, moderator_id: int, action: str, target_user_id: int, 
                   comment_id: int = None, details: str = None,
                   analysis_data: dict = None):
        log = ModeratorLog(
            moderator_id=moderator_id,
            action=action,
            target_user_id=target_user_id,
            comment_id=comment_id,
            details=details,
            analysis_data=analysis_data
        )
        self.session.add(log)
        self.session.commit()

    def get_moderation_stats(self, from_date: datetime = None) -> dict:
        query = self.session.query(ModeratorLog)
        if from_date:
            query = query.filter(ModeratorLog.created_at >= from_date)
            
        stats = {
            'total_actions': query.count(),
            'approved_comments': query.filter(ModeratorLog.action == 'approve_comment').count(),
            'rejected_comments': query.filter(ModeratorLog.action == 'reject_comment').count(),
            'warnings_issued': query.filter(ModeratorLog.action == 'warning_issued').count(),
            'users_banned': query.filter(ModeratorLog.action == 'user_banned').count(),
            'users_blacklisted': query.filter(ModeratorLog.action == 'user_blacklisted').count(),
            'suspicious_edits': query.filter(ModeratorLog.action == 'suspicious_edit').count()
        }
        return stats
        
    def get_user_history(self, user_id: int) -> dict:
        """Получение истории действий пользователя"""
        user = self.session.query(User).filter_by(telegram_id=user_id).first()
        if not user:
            return None
            
        return {
            'warnings_count': user.warnings_count,
            'suspicious_edits': user.suspicious_edits_count,
            'total_comments': self.session.query(Comment).filter_by(user_id=user.id).count(),
            'rejected_comments': self.session.query(Comment).filter_by(
                user_id=user.id, status='rejected'
            ).count(),
            'last_activity': user.last_activity,
            'is_restricted': user.edit_restrictions,
            'is_banned': user.is_banned,
            'ban_until': user.ban_until
        } 