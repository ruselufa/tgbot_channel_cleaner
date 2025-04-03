from datetime import datetime, timedelta
import logging
from sqlalchemy.orm import Session
from src.models import User, Warning
from config.settings import MAX_WARNINGS, BAN_DURATION

class UserService:
    def __init__(self, session: Session):
        self.session = session
        self.logger = logging.getLogger(__name__)

    async def get_or_create_user(self, telegram_id: int, username: str = None) -> User:
        """Получение или создание пользователя"""
        try:
            user = self.session.query(User).filter_by(telegram_id=telegram_id).first()
            
            if not user:
                user = User(
                    telegram_id=telegram_id,
                    username=username,
                    warning_count=0,
                    suspicious_edits_count=0
                )
                self.session.add(user)
                self.session.commit()
                
            return user
            
        except Exception as e:
            self.logger.error(f"Error in get_or_create_user: {e}")
            self.session.rollback()
            raise

    async def increment_warning_count(self, user_id: int) -> int:
        """Увеличение счетчика предупреждений"""
        try:
            user = self.session.query(User).filter_by(telegram_id=user_id).first()
            if not user:
                raise ValueError(f"User {user_id} not found")
                
            user.warning_count += 1
            self.session.commit()
            
            return user.warning_count
            
        except Exception as e:
            self.logger.error(f"Error in increment_warning_count: {e}")
            self.session.rollback()
            raise

    async def ban_user(self, user_id: int, duration_hours: int = 24) -> None:
        """Бан пользователя"""
        try:
            user = self.session.query(User).filter_by(telegram_id=user_id).first()
            if not user:
                raise ValueError(f"User {user_id} not found")
                
            user.is_banned = True
            user.ban_end_time = datetime.utcnow() + timedelta(hours=duration_hours)
            self.session.commit()
            
            self.logger.info(f"User {user_id} banned until {user.ban_end_time}")
            
        except Exception as e:
            self.logger.error(f"Error in ban_user: {e}")
            self.session.rollback()
            raise

    async def unban_user(self, user_id: int) -> None:
        """Разбан пользователя"""
        try:
            user = self.session.query(User).filter_by(telegram_id=user_id).first()
            if not user:
                raise ValueError(f"User {user_id} not found")
                
            user.is_banned = False
            user.ban_end_time = None
            self.session.commit()
            
            self.logger.info(f"User {user_id} unbanned")
            
        except Exception as e:
            self.logger.error(f"Error in unban_user: {e}")
            self.session.rollback()
            raise

    async def is_banned(self, user_id: int) -> bool:
        """Проверка бана пользователя"""
        try:
            user = self.session.query(User).filter_by(telegram_id=user_id).first()
            if not user:
                return False
                
            # Если пользователь забанен и время бана не истекло
            if user.is_banned and user.ban_end_time:
                if user.ban_end_time > datetime.utcnow():
                    return True
                else:
                    # Если время бана истекло, разбаниваем
                    await self.unban_user(user_id)
                    return False
                    
            return False
            
        except Exception as e:
            self.logger.error(f"Error in is_banned: {e}")
            return False

    async def reset_warnings(self, user_id: int) -> None:
        """Сброс предупреждений пользователя"""
        try:
            user = self.session.query(User).filter_by(telegram_id=user_id).first()
            if not user:
                raise ValueError(f"User {user_id} not found")
                
            user.warning_count = 0
            self.session.commit()
            
            self.logger.info(f"Warnings reset for user {user_id}")
            
        except Exception as e:
            self.logger.error(f"Error in reset_warnings: {e}")
            self.session.rollback()
            raise

    def check_user_restrictions(self, user: User) -> tuple[bool, str]:
        """Проверка ограничений пользователя"""
        if user.is_banned:
            if user.ban_end_time and user.ban_end_time > datetime.utcnow():
                return False, f"Вы заблокированы до {user.ban_end_time.strftime('%Y-%m-%d %H:%M:%S')}"
            else:
                user.is_banned = False
                user.ban_end_time = None
                self.session.commit()
                
        return True, ""

    async def add_warning(self, user_id: int, reason: str = "нарушение правил") -> int:
        """Добавление предупреждения пользователю"""
        try:
            user = await self.get_or_create_user(user_id)
            
            # Создаем запись о предупреждении
            warning = Warning(
                user_id=user.id,
                reason=reason,
                created_at=datetime.utcnow()
            )
            self.session.add(warning)
            
            # Увеличиваем счетчик предупреждений
            user.warning_count += 1
            
            # Если достигнут лимит предупреждений, баним пользователя
            if user.warning_count >= MAX_WARNINGS:
                user.is_banned = True
                user.banned_until = datetime.utcnow() + timedelta(hours=BAN_DURATION)
                
            self.session.commit()
            return user.warning_count
            
        except Exception as e:
            self.logger.error(f"Error adding warning: {e}")
            self.session.rollback()
            raise

    def add_to_blacklist(self, user: User):
        user.is_in_blacklist = True
        self.session.commit()
        
    def check_edit_restrictions(self, user: User) -> tuple[bool, str]:
        """Проверка ограничений на редактирование"""
        try:
            if user.banned_until and user.banned_until > datetime.utcnow():
                return False, "Вы заблокированы и не можете редактировать сообщения"
                
            if user.suspicious_edits_count >= 3:
                return False, "Вы превысили лимит подозрительных изменений"
                
            return True, ""
            
        except Exception as e:
            self.logger.error(f"Error checking edit restrictions: {e}")
            return False, "Произошла ошибка при проверке ограничений"

    def update_suspicious_edits_count(self, user: User) -> None:
        """Обновление счетчика подозрительных изменений"""
        try:
            user.suspicious_edits_count += 1
            self.session.commit()
        except Exception as e:
            self.logger.error(f"Error updating suspicious edits count: {e}")
            self.session.rollback()
            raise 