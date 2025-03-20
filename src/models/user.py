from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Boolean
from sqlalchemy.orm import relationship
from .base import Base

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True)
    username = Column(String(255))
    warnings_count = Column(Integer, default=0)
    is_banned = Column(Boolean, default=False)
    ban_until = Column(DateTime, nullable=True)
    is_in_blacklist = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_activity = Column(DateTime, default=datetime.utcnow)
    edit_restrictions = Column(Boolean, default=False)
    suspicious_edits_count = Column(Integer, default=0)
    
    comments = relationship("Comment", back_populates="user")
    warnings = relationship("Warning", back_populates="user")
    edit_history = relationship("MessageEdit", back_populates="user") 