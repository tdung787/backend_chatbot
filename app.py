import uvicorn
import json
import re
import os
import openai
import shutil
import streamlit as st
from pathlib import Path
from sqlalchemy.orm import Session
from database.db import get_db
from database.api import router as auth_router
from datetime import datetime
from pydantic import BaseModel, EmailStr, HttpUrl
from fastapi import FastAPI, Query, Depends, HTTPException, BackgroundTasks, UploadFile, File, Form
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from src.conversation_engine import initialize_chatbot, chat_response, load_chat_store
from database.models import User, ActiveToken, ChatSession ,ChatMessage
from database.auth import verify_password, create_access_token, verify_token
from database.tracking import update_tracking_data
from llama_index.core.storage.chat_store import SimpleChatStore
from typing import List, Optional, Union
from llama_index.llms.openai import OpenAI
from llama_index.core import Settings

openai.api_key = st.secrets.openai.OPENAI_API_KEY
openai_llm = OpenAI(model="gpt-4o", max_new_tokens=900, temperature=0.2)

app = FastAPI()

app.mount("/static", StaticFiles(directory="data/images"), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

current_session_id = None

@app.on_event("startup")
def startup_event():
    global agent
    chat_store = SimpleChatStore()
    agent = initialize_chatbot(chat_store) 

    images_dir = "data/images"
    os.makedirs(images_dir, exist_ok=True)

def cleanup_expired_tokens(db: Session):
    """Xóa token đã hết hạn khỏi database"""
    now = datetime.utcnow()
    db.query(ActiveToken).filter(ActiveToken.expires_at < now).delete()
    db.commit()

class ChatMessageSchema(BaseModel):
    id: int
    role: str
    content: str
    timestamp: datetime

    class Config:
        orm_mode = True

class ChatSessionSchema(BaseModel):
    id: int
    title: str
    created_at: datetime
    messages: List[ChatMessageSchema] = []

    class Config:
        orm_mode = True

class MessageInput(BaseModel):
    session_id: int
    text: Union[str, List[dict]]  # Chấp nhận string hoặc list chứa text + image_url
    image_url: Optional[HttpUrl] = None

class CreateSessionInput(BaseModel):
    user_id: int
    title: str

class Message(BaseModel):
    role: str
    content: str
    additional_kwargs: dict = {}

class UserLogin(BaseModel):
    email: EmailStr
    password: str

# Login API
@app.post("/auth/login")
def login_user(background_tasks: BackgroundTasks, user: UserLogin, db: Session = Depends(get_db)):
    global current_session_id

    db_user = db.query(User).filter(User.email == user.email).first()
    if not db_user or not verify_password(user.password, db_user.hashed_password):
        raise HTTPException(status_code=401, detail="Sai email hoặc mật khẩu")

    # Cập nhật token payload
    token_data = {
        "sub": db_user.id,
        "ho_va_ten": db_user.ho_va_ten,  
        "noi_o": db_user.noi_o 
    }

    token = create_access_token(token_data, db=db)  
    update_tracking_data(db)

    background_tasks.add_task(cleanup_expired_tokens, db)

    global agent
    chat_store = SimpleChatStore()
    agent = initialize_chatbot(chat_store, user_id=token_data["sub"])

    # Kiểm tra xem user đã có session "New chat" chưa
    existing_session = (
        db.query(ChatSession)
        .filter(ChatSession.user_id == token_data["sub"], ChatSession.title == "New chat")
        .first()
    )

    if existing_session:
        current_session_id = existing_session.id
    else:
        new_session = ChatSession(
            user_id=db_user.id,
            title="New chat",
            # created_at=datetime.utcnow(),
        )
        db.add(new_session)
        db.commit()
        db.refresh(new_session)
        current_session_id = new_session.id
    
    return {
        "user": token_data, 
        "access_token": token, 
        "token_type": "bearer",
        "session_id": current_session_id,  
        "session_title": "New chat"  
    }

#Response API
@app.post("/query")
async def chat_api(
    session_id: int = Form(..., description="Session ID của người dùng"),
    text: str = Form(..., description="Câu hỏi gửi đến AI"),
    image: UploadFile = File(None),  
    db: Session = Depends(get_db),
    authorized: bool = Depends(verify_token),
):
    """API nhận câu hỏi + hình ảnh và gửi vào agent."""

    # Kiểm tra session
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        return JSONResponse(content={"error": "Session không tồn tại"}, status_code=404)
    
    # Cập nhật tiêu đề session
    session.title = re.sub(r'[^\w\s]', '', text)[:20]  
    db.commit()

    # Nếu có hình ảnh, lưu tệp vào thư mục `data/pictures/`
    img_path = None
    if image:
        img_dir = Path("data/pictures")
        img_dir.mkdir(parents=True, exist_ok=True)  # Đảm bảo thư mục tồn tại
        img_path = img_dir / image.filename
        with img_path.open("wb") as buffer:
            shutil.copyfileobj(image.file, buffer)

    # Gửi vào agent (có hoặc không có ảnh)
    if img_path:
        prompt = f"image_tool('{img_path}', '{text}')"
    else:
        prompt = text

    search_keywords = ["tìm kiếm", "tra cứu", "thông tin về", "google", "search"]
    is_search_query = any(keyword in text.lower() for keyword in search_keywords)

    if is_search_query:
        prompt = f"webSearch_tool('{text}')"
    else:
        prompt = text

    response = chat_response(agent, prompt, session_id, db)

    return JSONResponse(content={"text": response, "session_id": session_id})


#Lưu cuộc hội thoại
@app.get("/chat_store")
def get_chat_store(
    db: Session = Depends(get_db),
    payload: dict = Depends(verify_token)
):  
    global agent, current_session_id

    if current_session_id is None:
        raise HTTPException(status_code=400, detail="Không có session nào. Hãy đăng nhập trước.")

    chat_store = load_chat_store(current_session_id, db, payload)
    agent = initialize_chatbot(chat_store, user_id=payload["user_id"])

    return {
        "store": chat_store.store,
        "class_name": "SimpleChatStore",
        "current_session_id": current_session_id
    }


#API Lấy thông tin số người online và tổng số truy cập
@app.get("/tracking")
def get_tracking_data():
    try:
        json_path = Path("data/tracking.json")
        
        if not json_path.exists():
            return JSONResponse(
                content={
                    "Active_user": 0,
                    "Total_visit": 0
                },
                status_code=200
            )
        
        with open(json_path, 'r', encoding='utf-8') as f:
            tracking_data = json.load(f)
            
        return JSONResponse(content=tracking_data, status_code=200)
            
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Không thể đọc dữ liệu tracking: {str(e)}"
        )
    
#API lấy lịch sử chat (Lấy thông tin lịch sử chat của user hiện tại)
@app.get("/chat/user/{user_id}", response_model=dict)
def get_chat_sessions(user_id: int, db: Session = Depends(get_db)):
    """Lấy danh sách các phiên chat của user, sắp xếp theo thời gian mới nhất trước"""
    sessions = db.query(ChatSession.id, ChatSession.title, ChatSession.created_at)\
                 .filter(ChatSession.user_id == user_id)\
                 .order_by(ChatSession.created_at.desc())\
                 .all()
    
    return {
        "title_list": [
            {"session_id": session.id, "title": session.title, "timestamp": session.created_at}
            for session in sessions
        ]
    }

#API lấy thông tin lịch sử chat (Lấy thông tin của cuộc hội thoại với current_session_id)
@app.get("/chat/session/{session_id}", response_model=ChatSessionSchema)
def get_chat_session(session_id: int, db: Session = Depends(get_db)):
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()

    if not session:
        # Ném ngoại lệ HTTPException với mã lỗi 404 và thông báo lỗi
        raise HTTPException(status_code=404, detail="Không tìm thấy session")

    return session



#API tạo đoạn chat mới
@app.post("/chat/create_session")
def create_chat_session(
    db: Session = Depends(get_db),
    payload: dict = Depends(verify_token)  # Lấy user từ token
):
    """Tạo một phiên trò chuyện mới hoặc lấy phiên hiện có với tiêu đề 'New chat'"""
    global current_session_id  
    
    # Tìm session có tiêu đề "New chat" của user hiện tại
    existing_session = (
        db.query(ChatSession)
        .filter(ChatSession.user_id == payload["user_id"], ChatSession.title == "New chat")
        .first()
    )

    if existing_session:
        current_session_id = existing_session.id
    else:
        new_session = ChatSession(
            user_id=payload["user_id"],  # Lấy user_id từ token
            title="New chat",
            # created_at=datetime.utcnow(),
        )

        db.add(new_session)
        db.commit()
        db.refresh(new_session)
        
        current_session_id = new_session.id  
    
    return {
        "session_id": current_session_id,
        "user_id": payload["user_id"],
        "current_session_id": current_session_id,
    }

@app.delete("/chat/delete_session/{session_id}")
def delete_chat_session(
    session_id: int,  # Nhận session_id từ URL
    db: Session = Depends(get_db),
    payload: dict = Depends(verify_token)  # Lấy user từ token
):
    """Xóa một phiên trò chuyện và tất cả các tin nhắn liên quan."""
    
    # Kiểm tra sự tồn tại của session và xem nó có thuộc về user hiện tại không
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id, 
        ChatSession.user_id == payload["user_id"]
    ).first()

    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found or not belongs to the user")

    # Xóa tất cả các tin nhắn liên quan đến session này
    db.query(ChatMessage).filter(ChatMessage.session_id == session_id).delete()

    # Xóa phiên trò chuyện (ChatSession)
    db.delete(session)
    db.commit()

    return {"message": "Đã xóa thành công!"}


app.include_router(auth_router, prefix="/auth", tags=["Authentication"])

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5601)
