from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Float, ForeignKey, JSON
from sqlalchemy.orm import relationship
from .base import Base

class MessageEdit(Base):
    __tablename__ = 'message_edits'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    message_id = Column(Integer, nullable=False)
    old_text = Column(String)
    new_text = Column(String)
    sentiment_change = Column(Float)
    is_suspicious = Column(Boolean, default=False)
    analysis_data = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="edit_history") 