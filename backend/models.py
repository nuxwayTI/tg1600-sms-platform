from sqlalchemy import Column, Integer, String, Text, DateTime
from datetime import datetime
from database import Base


class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    message_text = Column(Text, nullable=False)
    chips = Column(String(255), nullable=False)
    status = Column(String(50), default="active")
    created_at = Column(DateTime, default=datetime.utcnow)


class SmsMessage(Base):
    __tablename__ = "sms_messages"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, index=True)
    phone = Column(String(50), nullable=False)
    text = Column(Text, nullable=False)
    chip = Column(Integer, nullable=False)
    status = Column(String(50), default="queued")
    result = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    sent_at = Column(DateTime, nullable=True)
