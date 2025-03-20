from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Text, JSON, Float
from sqlalchemy.orm import relationship
from .base import Base

class MessageEdit(Base):
    __tablename__ = 'message_edits'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    comment_id = Column(Integer, ForeignKey('comments.id'))
    old_text = Column(Text)
    new_text = Column(Text)
    sentiment_change = Column(Float)
    is_suspicious = Column(Boolean, default=False)
    analysis_data = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    action_taken = Column(String(50), nullable=True)  # deleted, approved, rejected
    
    user = relationship("User", back_populates="edit_history")
    comment = relationship("Comment", back_populates="edits") 