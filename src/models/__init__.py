from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Float, Text
from sqlalchemy.orm import relationship, sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import create_engine
from datetime import datetime
from config.settings import DATABASE_URL

Base = declarative_base()

# Создаем подключение к базе данных
engine = create_engine(DATABASE_URL)

# Создаем фабрику сессий
Session = sessionmaker(bind=engine)

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True)
    username = Column(String(255))
    warning_count = Column(Integer, default=0)
    suspicious_edits_count = Column(Integer, default=0)
    is_banned = Column(Boolean, default=False)
    banned_until = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    warnings = relationship("Warning", back_populates="user")
    comments = relationship("Comment", back_populates="user")

class Warning(Base):
    __tablename__ = 'warnings'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    reason = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="warnings")

class Comment(Base):
    __tablename__ = 'comments'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    post_id = Column(Integer)
    text = Column(Text)
    sentiment_score = Column(Float)
    toxicity_score = Column(Float)
    is_approved = Column(Boolean, default=False)
    is_rejected = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    user = relationship("User", back_populates="comments")
    edits = relationship("MessageEdit", back_populates="comment")

class MessageEdit(Base):
    __tablename__ = 'message_edits'
    
    id = Column(Integer, primary_key=True)
    comment_id = Column(Integer, ForeignKey('comments.id'))
    old_text = Column(Text)
    new_text = Column(Text)
    sentiment_change = Column(Float)
    is_suspicious = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    comment = relationship("Comment", back_populates="edits")

class ModeratorLog(Base):
    __tablename__ = 'moderator_logs'
    
    id = Column(Integer, primary_key=True)
    moderator_id = Column(Integer, ForeignKey('users.id'))
    action = Column(String(50))  # approve, reject, ban, etc.
    target_type = Column(String(50))  # comment, user, etc.
    target_id = Column(Integer)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    moderator = relationship("User", foreign_keys=[moderator_id])

__all__ = [
    'Base',
    'Session',
    'User',
    'Warning',
    'Comment',
    'MessageEdit',
    'ModeratorLog'
] 