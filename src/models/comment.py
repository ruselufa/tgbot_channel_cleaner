from datetime import datetime
from sqlalchemy import Column, Integer, Text, Boolean, DateTime, ForeignKey, Float, String
from sqlalchemy.orm import relationship
from .base import Base

class Comment(Base):
    __tablename__ = 'comments'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    post_id = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
    sentiment_score = Column(Float)
    toxicity_score = Column(Float)
    is_approved = Column(Boolean, default=False)
    is_rejected = Column(Boolean, default=False)
    rejection_reason = Column(String(255))
    moderator_id = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Связи с другими таблицами
    user = relationship("User", back_populates="comments")
    edits = relationship("CommentEdit", back_populates="comment") 