from datetime import datetime
from sqlalchemy import Column, Integer, BigInteger, String, DateTime, Boolean
from sqlalchemy.orm import relationship
from .base import Base

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False)
    username = Column(String(255))
    warnings_count = Column(Integer, default=0)
    is_banned = Column(Boolean, default=False)
    ban_end_time = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_in_blacklist = Column(Boolean, default=False)
    last_activity = Column(DateTime, default=datetime.utcnow)
    edit_restrictions = Column(Boolean, default=False)
    suspicious_edits_count = Column(Integer, default=0)
    
    messages = relationship("Message", back_populates="user")
    comments = relationship("Comment", back_populates="user")
    edit_history = relationship("MessageEdit", back_populates="user") 