import os
import re
import openai
import uuid
import streamlit as st
from datetime import datetime
from llama_index.core import Settings
from llama_index.llms.openai import OpenAI
from llama_index.core import load_index_from_storage, StorageContext
from llama_index.core.memory import ChatMemoryBuffer
from llama_index.core.tools import QueryEngineTool, ToolMetadata
from llama_index.agent.openai import OpenAIAgent
from llama_index.core.storage.chat_store import SimpleChatStore
from llama_index.core.tools import FunctionTool, ToolMetadata
from sqlalchemy.orm import Session
from database.models import ChatMessage
from src.global_settings import INDEX_STORAGE
from src.prompts import CUSTORM_AGENT_SYSTEM_TEMPLATE
import numpy as np
import sympy as sp
import matplotlib.pyplot as plt
from sympy import Rational, latex
from fastapi import HTTPException
from flask import url_for

openai.api_key = st.secrets.openai.OPENAI_API_KEY
Settings.llm = OpenAI(model="gpt-4o", temperature=0.2)

def generate_unique_filename():
    """Generate a unique filename with timestamp and random UUID."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    random_id = str(uuid.uuid4())[:8]  # Using first 8 characters of UUID
    return f"{timestamp}_{random_id}.png"


def save_plot():
    image_dir = "data/images"
    if not os.path.exists(image_dir):
        os.makedirs(image_dir)
    filename = generate_unique_filename()
    img_path = os.path.join(image_dir, filename)
    plt.savefig(img_path)
    plt.close()
    return {
        "type": "image",
        "url": f"/static/{filename}"
    }

def sanitize_input(expression):
    """Chuẩn hóa biểu thức đầu vào."""
    expression = re.sub(r'[^\x00-\x7F]+', '', expression).strip()
    expression = re.sub(r'(?<=\d)(?=[a-zA-Z])', '*', expression)
    expression = re.sub(r'(?<=[a-zA-Z])(?=\d)', '*', expression)
    return expression

def extract_rational_parts(expression):
    """Tách tử số và mẫu số từ biểu thức phân thức."""
    x = sp.Symbol('x')
    expr = sp.sympify(expression)
    if expr.is_rational_function(x):
        numerator, denominator = sp.fraction(expr)
        return str(numerator), str(denominator)
    else:
        raise ValueError("Biểu thức không phải là hàm phân thức hợp lệ")
    
def calculate_horizontal_asymptote(numerator_expr, denominator_expr):
    """Tính tiệm cận ngang."""
    x = sp.Symbol('x')
    numerator = sp.sympify(numerator_expr)
    denominator = sp.sympify(denominator_expr)
    limit = sp.limit(numerator / denominator, x, sp.oo)
    return float(limit) if limit.is_real else None

def find_vertical_asymptotes(denominator_expr):
    """Tìm tiệm cận đứng."""
    x = sp.Symbol('x')
    denominator = sp.sympify(denominator_expr)
    return [float(sol) for sol in sp.solve(denominator, x) if sp.im(sol) == 0]


def calculate_derivative(expression):
    """Tính đạo hàm của biểu thức."""
    x = sp.Symbol('x')
    expr = sp.sympify(expression)
    derivative = sp.diff(expr, x)
    return derivative

def find_extrema(expression):
    """Tìm cực tiểu và cực đại của hàm số bằng cách giải phương trình đạo hàm."""
    x = sp.Symbol('x')
    expr = sp.sympify(expression)
    derivative = sp.diff(expr, x)
    critical_points = sp.solve(derivative, x)
    
    extrema = []
    for point in critical_points:
        if point.is_real:
            second_derivative = sp.diff(derivative, x)
            concavity = second_derivative.subs(x, point)
            
            if concavity > 0:
                extrema.append((float(point), float(expr.subs(x, point)), "Cực tiểu"))  # Cực tiểu
            elif concavity < 0:
                extrema.append((float(point), float(expr.subs(x, point)), "Cực đại"))  # Cực đại
    
    return extrema


def generate_plot(expression: str, show_asymptotes: bool = False, show_derivative: bool = False, show_extrema: bool = False):
    """
    Tạo đồ thị hàm phân thức và đạo hàm của nó.
    
    Args:
        expression (str): Biểu thức hàm phân thức
        show_asymptotes (bool): Có hiển thị đường tiệm cận hay không
        show_derivative (bool): Có hiển thị đồ thị đạo hàm hay không
        show_extrema (bool): Có hiển thị điểm cựu trị hay không
    """
    try:
        expression = sanitize_input(expression)
        numerator, denominator = extract_rational_parts(expression)

        x = sp.Symbol('x')
        num_expr = sp.sympify(numerator)
        den_expr = sp.sympify(denominator)
        expr = num_expr / den_expr

        # Tính đạo hàm
        if show_derivative:
            derivative = calculate_derivative(expr)

        vertical_asymptotes = find_vertical_asymptotes(den_expr)
        horizontal_asymptote = calculate_horizontal_asymptote(num_expr, den_expr)
        extrema_points = find_extrema(num_expr / den_expr) if show_extrema else []
        fig, ax = plt.subplots()

        # Xử lý tiệm cận đứng
        x_ranges = []
        if vertical_asymptotes:
            vas = sorted(vertical_asymptotes)
            if vas[0] > -10:
                x_ranges.append(np.linspace(-10, vas[0] - 0.1, 200))
            for i in range(len(vas) - 1):
                x_ranges.append(np.linspace(vas[i] + 0.1, vas[i+1] - 0.1, 200))
            if vas[-1] < 10:
                x_ranges.append(np.linspace(vas[-1] + 0.1, 10, 200))
        else:
            x_ranges.append(np.linspace(-10, 10, 1000))

        # Vẽ hàm gốc
        for x_range in x_ranges:
            y_points = [float(expr.subs(x, xi)) for xi in x_range]
            y_points = np.array(y_points)

            expression_sympy = sp.sympify(expression)
            expression_latex = r"$f(x) = " + latex(expression_sympy) + r"$"

            valid_points = ~np.isnan(y_points) & ~np.isinf(y_points)
            if any(valid_points):
                ax.plot(x_range[valid_points], y_points[valid_points], 'b-', 
                        label=expression_latex if x_range is x_ranges[0] else "")

        # Vẽ đạo hàm nếu được yêu cầu
        if show_derivative:
            for x_range in x_ranges:
                y_derivative = [float(derivative.subs(x, xi)) for xi in x_range]
                y_derivative = np.array(y_derivative)

                derivative_latex = r"$f'(x) = " + latex(derivative) + r"$"

                valid_points = ~np.isnan(y_derivative) & ~np.isinf(y_derivative)
                if any(valid_points):   
                    ax.plot(x_range[valid_points], y_derivative[valid_points], 'r--',   
                            linestyle='--', label=derivative_latex if x_range is x_ranges[0] else "")   
    

        # Xử lý giới hạn trục y
        all_y_points = []
        for x_range in x_ranges:
            y_points = [float(expr.subs(x, xi)) for xi in x_range]
            if show_derivative:
                y_derivative = [float(derivative.subs(x, xi)) for xi in x_range]
                all_y_points.extend(y_derivative)
            all_y_points.extend(y_points)
        
        all_y_points = np.array(all_y_points)
        valid_points = ~np.isnan(all_y_points) & ~np.isinf(all_y_points)
        if any(valid_points):
            y_filtered = all_y_points[valid_points]
            y_min = max(-35, y_filtered.min())
            y_max = min(35, y_filtered.max())
            ax.set_ylim(y_min, y_max)
            
        # Vẽ tiệm cận
        if show_asymptotes:
            if vertical_asymptotes:
                for va in vertical_asymptotes:
                    va_fraction = Rational(va).limit_denominator()
                    va_latex = f"Tiệm cận đứng $x = {latex(va_fraction)}$"
                    ax.axvline(x=va, color='r', linestyle='--', alpha=0.8, label=va_latex)

            if horizontal_asymptote is not None:
                ha_fraction = Rational(horizontal_asymptote).limit_denominator()
                ha_latex = f"Tiệm cận ngang $y = {latex(ha_fraction)}$"
                ax.axhline(y=horizontal_asymptote, color='g', linestyle='--', alpha=0.8, label=ha_latex)

            if show_extrema and extrema_points:
                for x_ext, y_ext, ext_type in extrema_points:
                    ax.scatter(x_ext, y_ext, color='red', zorder=3, marker='x', label=f"{ext_type} tại x={x_ext:.2f}, y={y_ext:.2f}")


        title = r'Đồ thị của hàm số và đạo hàm' if show_derivative else r'Đồ thị của hàm số'
        ax.set_title(title, pad=5, fontsize=14, y=1.05)
        
        ax.grid(True)
        ax.set_xlabel('x')
        ax.set_ylabel('y')
        ax.axhline(y=0, color='k', linestyle='-', linewidth=0.5)
        ax.axvline(x=0, color='k', linestyle='-', linewidth=0.5)

        # Hiển thị legend
        ax.legend()

        return save_plot()

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

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

def initialize_chatbot(chat_store, user_id=None):
    """Khởi tạo chatbot với cấu hình."""
    if user_id is None:
        user_id = "guest"  #có thể có vấn đề về việc bỏ qua đăng nhập
        
    # Tạo bộ nhớ chatbot và load dữ liệu
    memory = ChatMemoryBuffer.from_defaults(
        token_limit=3000, 
        chat_store=chat_store, 
        chat_store_key=str(user_id)
    )
    
    storage_context = StorageContext.from_defaults(persist_dir=INDEX_STORAGE)
    index = load_index_from_storage(storage_context, index_id="vector")
    query_engine = index.as_query_engine(similarity_top_k=2)
     
    plot_tool = FunctionTool.from_defaults(
        fn=lambda expression, show_asymptotes=True, show_derivative=False, show_extrema=True: generate_plot(
            expression, 
            show_asymptotes=show_asymptotes, 
            show_derivative=show_derivative,
            show_extrema=show_extrema
        ),
        name="generate_plot",
        description="Vẽ đồ thị của hàm số, chỉ 1 hình duy nhất. Tham số show_asymptotes để chọn có hiển thị đường tiệm cận hay không, show_derivative để chọn có hiển thị đạo hàm hay không, show_extrema để chọn có hiển thị điểm cực trị hay không"
        
    )
    query_tool = QueryEngineTool(
        query_engine=query_engine, 
        metadata=ToolMetadata(
            name="query",
            description="Cung cấp câu hỏi và đáp án môn toán."
        )
    )
    agent = OpenAIAgent.from_tools(
        tools=[query_tool, plot_tool], 
        memory=memory,
        system_prompt=CUSTORM_AGENT_SYSTEM_TEMPLATE
    )
    return agent

def chat_response(agent, prompt: str, session_id: int, db: Session):
    """Nhận prompt và trả về phản hồi từ AI, đồng thời lưu tin nhắn vào database."""

    user_message = ChatMessage(
        session_id=session_id,
        role="user",
        content=prompt,
    )
    db.add(user_message)
    db.commit()

    ai_response = str(agent.chat(prompt))

    ai_message = ChatMessage(
        session_id=session_id,
        role="assistant",
        content=ai_response,
    )
    db.add(ai_message)
    db.commit()

    return ai_response
