from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from models import User, Warning
from config import MAX_WARNINGS, BAN_DURATION

class UserService:
    def __init__(self, session: Session):
        self.session = session

    def get_or_create_user(self, telegram_id: int, username: str) -> User:
        user = self.session.query(User).filter_by(telegram_id=telegram_id).first()
        if not user:
            user = User(telegram_id=telegram_id, username=username)
            self.session.add(user)
            self.session.commit()
        return user

    def check_user_restrictions(self, user: User) -> tuple[bool, str]:
        user.last_activity = datetime.utcnow()
        self.session.commit()
        
        if user.is_in_blacklist:
            return False, "Пользователь в черном списке"
        
        if user.is_banned:
            if user.ban_until and user.ban_until > datetime.utcnow():
                return False, f"Пользователь заблокирован до {user.ban_until}"
            else:
                user.is_banned = False
                self.session.commit()
        
        return True, ""

    def add_warning(self, user: User, reason: str) -> tuple[int, bool]:
        warning = Warning(
            user_id=user.id,
            reason=reason,
            expires_at=datetime.utcnow() + timedelta(days=30)
        )
        self.session.add(warning)
        user.warnings_count += 1
        
        should_ban = False
        if user.warnings_count >= MAX_WARNINGS:
            user.is_banned = True
            user.ban_until = datetime.utcnow() + timedelta(seconds=BAN_DURATION)
            should_ban = True
            
        self.session.commit()
        return user.warnings_count, should_ban

    def add_to_blacklist(self, user: User):
        user.is_in_blacklist = True
        self.session.commit()
        
    def check_edit_restrictions(self, user: User) -> tuple[bool, str]:
        """Проверка ограничений на редактирование"""
        if user.edit_restrictions:
            return False, "Редактирование сообщений ограничено"
        return True, ""
        
    def update_suspicious_edits_count(self, user: User):
        """Обновление счетчика подозрительных изменений"""
        user.suspicious_edits_count += 1
        if user.suspicious_edits_count >= 3:
            user.edit_restrictions = True
        self.session.commit() 