import os
import json
import re
import openai
import streamlit as st
from datetime import datetime
from pydantic import ValidationError
from llama_index.core import Settings
from llama_index.llms.openai import OpenAI
from llama_index.core import load_index_from_storage
from llama_index.core import StorageContext
from llama_index.core.memory import ChatMemoryBuffer
from llama_index.core.tools import QueryEngineTool, ToolMetadata
from llama_index.agent.openai import OpenAIAgent
from llama_index.core.storage.chat_store import SimpleChatStore
from llama_index.core.tools import FunctionTool, ToolMetadata
from sqlalchemy.orm import Session
from database.models import ChatMessage, ChatSession, User
from src.global_settings import INDEX_STORAGE
from src.prompts import CUSTORM_AGENT_SYSTEM_TEMPLATE

openai.api_key = st.secrets.openai.OPENAI_API_KEY
Settings.llm = OpenAI(model="gpt-4o", temperature=0.2)


def load_chat_store(session_id: int, db: Session, payload: dict):
    """Load hoặc tạo mới một chat store từ database dựa trên session_id."""
    chat_store = SimpleChatStore()

    # Lấy tin nhắn từ database
    messages = db.query(ChatMessage).filter(ChatMessage.session_id == session_id).all()

    # Lấy họ và tên từ payload (token) thay vì từ messages[0].user
    ho_va_ten = payload.get("ho_va_ten", "Unknown User")

    if messages:
        formatted_messages = [{
            "role": msg.role,
            "content": msg.content,
            "additional_kwargs": {}
        } for msg in messages]

        chat_store.store = {ho_va_ten: formatted_messages}

    return chat_store

def initialize_chatbot(chat_store, user_id: int):
    """Khởi tạo chatbot với cấu hình."""

    # Tạo bộ nhớ chatbot và load dữ liệu
    memory = ChatMemoryBuffer.from_defaults(
        token_limit=3000, 
        chat_store=chat_store, 
        chat_store_key=str(user_id)
    )
    
    storage_context = StorageContext.from_defaults(persist_dir=INDEX_STORAGE)
    index = load_index_from_storage(storage_context, index_id="vector")
    query_engine = index.as_query_engine(similarity_top_k=2)
    query_tool = QueryEngineTool(
        query_engine=query_engine, 
        metadata=ToolMetadata(
            name="query",
            description="Cung cấp câu hỏi và đáp án môn toán."
        )
    )
    agent = OpenAIAgent.from_tools(
        tools=[query_tool], 
        memory=memory,
        system_prompt=CUSTORM_AGENT_SYSTEM_TEMPLATE
    )
    print(f"📚 Chat Store Data: {memory.chat_store}")
    return agent

def chat_response(agent, prompt: str, session_id: int, db: Session):
    """Nhận prompt và trả về phản hồi từ AI, đồng thời lưu tin nhắn vào database."""

    # 📝 Lưu tin nhắn của người dùng vào database
    user_message = ChatMessage(
        session_id=session_id,
        role="user",
        content=prompt,
    )
    db.add(user_message)
    db.commit()

    # 🤖 Nhận phản hồi từ chatbot
    ai_response = str(agent.chat(prompt))

    # 📝 Lưu tin nhắn của chatbot vào database
    ai_message = ChatMessage(
        session_id=session_id,
        role="assistant",
        content=ai_response,
    )
    db.add(ai_message)
    db.commit()

    return ai_response
