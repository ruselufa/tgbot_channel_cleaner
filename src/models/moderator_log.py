from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, JSON
from .base import Base

class ModeratorLog(Base):
    __tablename__ = 'moderator_logs'
    
    id = Column(Integer, primary_key=True)
    moderator_id = Column(Integer)
    action = Column(String(50))
    target_user_id = Column(Integer)
    comment_id = Column(Integer, nullable=True)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    analysis_data = Column(JSON, nullable=True) 