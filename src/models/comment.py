from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Float, Text
from sqlalchemy.orm import relationship
from .base import Base

class Comment(Base):
    __tablename__ = 'comments'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    post_id = Column(Integer)
    text = Column(Text)
    sentiment_score = Column(Float)
    status = Column(String(20))  # pending, approved, rejected
    moderated_by = Column(Integer, nullable=True)
    rejection_reason = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    moderated_at = Column(DateTime, nullable=True)
    is_edited = Column(Boolean, default=False)
    edit_count = Column(Integer, default=0)
    last_edit_at = Column(DateTime, nullable=True)
    
    user = relationship("User", back_populates="comments")
    edits = relationship("MessageEdit", back_populates="comment") 