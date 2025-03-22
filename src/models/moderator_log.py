from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey

from .base import Base

class ModeratorLog(Base):
    __tablename__ = 'moderator_logs'
    
    id = Column(Integer, primary_key=True)
    moderator_id = Column(Integer)
    action = Column(String(50), nullable=False)
    target_user_id = Column(Integer)
    comment_id = Column(Integer, ForeignKey('comments.id'))
    details = Column(Text)
    analysis_data = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow) 