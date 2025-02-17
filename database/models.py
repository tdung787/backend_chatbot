from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
import pytz
from .db import Base

VN_TZ = pytz.timezone("Asia/Ho_Chi_Minh")

def get_vietnam_time():
    """Trả về thời gian hiện tại ở Việt Nam với timezone information."""
    utc_now = datetime.utcnow()
    return utc_now.replace(tzinfo=pytz.UTC).astimezone(VN_TZ)

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    ho_va_ten = Column(String, index=True, nullable=False)
    sdt = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    facebook = Column(String, index=True, nullable=True)
    noi_o = Column(String, index=True, nullable=False)
    ten_truong = Column(String, index=True, nullable=False)
    hashed_password = Column(String)

class ActiveToken(Base):
    __tablename__ = "active_tokens"
    id = Column(Integer, primary_key=True, index=True)
    token = Column(String, unique=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    expires_at = Column(DateTime(timezone=True), default=get_vietnam_time)
    created_at = Column(DateTime(timezone=True), default=get_vietnam_time)
    user = relationship("User")

class ChatSession(Base):
    __tablename__ = "chat_sessions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=get_vietnam_time)
    messages = relationship("ChatMessage", back_populates="session")

class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id", ondelete="CASCADE"))
    role = Column(String)
    content = Column(String)
    timestamp = Column(DateTime(timezone=True), default=get_vietnam_time)
    session = relationship("ChatSession", back_populates="messages")
