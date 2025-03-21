import os
import re
import json
import openai
import uuid
import streamlit as st
from pathlib import Path
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
from database.models import ChatMessage as ChatMessageDB
from src.global_settings import INDEX_STORAGE
from src.prompts import CUSTORM_AGENT_SYSTEM_TEMPLATE
import numpy as np
import sympy as sp
from typing import Union
import matplotlib.pyplot as plt
from fastapi import HTTPException
from llama_index.core.llms import (
    ChatMessage,
    ImageBlock,
    TextBlock,
    MessageRole,
)

openai.api_key = st.secrets.openai.OPENAI_API_KEY
Settings.llm = OpenAI(model="gpt-4o-2024-11-20", temperature=0.2, max_new_tokens=1500)

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
        "url": f"http://127.0.0.1:5601/static/{filename}"
    }

def sanitize_input(expression):
    """Chuẩn hóa biểu thức đầu vào."""
    expression = re.sub(r'[^\x00-\x7F]+', '', expression).strip()
    expression = re.sub(r'(?<=\d)(?=[a-zA-Z])', '*', expression)
    expression = re.sub(r'(?<=[a-zA-Z])(?=\d)', '*', expression)
    return expression

def is_rational_function(expr):
    """Kiểm tra xem biểu thức có phải là hàm phân thức hay không."""
    x = sp.Symbol('x')
    try:
        num, den = sp.fraction(expr)
        # Nếu mẫu số là 1, đây không phải là phân thức
        if den == 1:
            return False
        return True
    except:
        return False

def extract_expression_parts(expr):
    """Tách tử số và mẫu số từ biểu thức."""
    x = sp.Symbol('x')
    try:
        num, den = sp.fraction(expr)
        return num, den
    except:
        return expr, sp.Integer(1)

def calculate_horizontal_asymptote(num, den):
    """Tính tiệm cận ngang."""
    x = sp.Symbol('x')
    try:
        # Nếu đây là hàm phân thức
        if den != 1:
            degree_num = sp.degree(num, x)
            degree_den = sp.degree(den, x)
            
            if degree_num < degree_den:
                return 0
            elif degree_num == degree_den:
                lc_num = sp.LC(num, x)
                lc_den = sp.LC(den, x)
                return float(lc_num / lc_den)
            else:
                # Nếu bậc tử > bậc mẫu, không có tiệm cận ngang
                return None
        else:
            # Hàm không phải phân thức, kiểm tra giới hạn vô cùng
            limit = sp.limit(num/den, x, sp.oo)
            if limit.is_real and not limit.is_infinite:
                return float(limit)
            return None
    except:
        # Thử tính bằng giới hạn nếu phương pháp trên không thành công
        try:
            limit = sp.limit(num/den, x, sp.oo)
            if limit.is_real and not limit.is_infinite:
                return float(limit)
        except:
            pass
        return None

def find_vertical_asymptotes(den):
    """Tìm tiệm cận đứng."""
    x = sp.Symbol('x')
    if den == 1:
        return []
    
    try:
        # Giải phương trình mẫu số = 0
        solutions = sp.solve(den, x)
        # Lọc các điểm là số thực
        vertical_asymptotes = [float(sol) for sol in solutions if sp.im(sol) == 0]
        return vertical_asymptotes
    except:
        return []

def calculate_derivative(expr):
    """Tính đạo hàm của biểu thức."""
    x = sp.Symbol('x')
    derivative = sp.diff(expr, x)
    return derivative

def find_extrema(expr):
    """Tìm cực tiểu và cực đại của hàm số."""
    x = sp.Symbol('x')
    derivative = sp.diff(expr, x)
    
    try:
        critical_points = sp.solve(derivative, x)
    except:
        return []
    
    extrema = []
    for point in critical_points:
        if point.is_real:
            try:
                point_float = float(point)
                y_value = float(expr.subs(x, point))
                
                # Kiểm tra đạo hàm bậc 2 để xác định loại điểm cực trị
                second_derivative = sp.diff(derivative, x)
                concavity = second_derivative.subs(x, point)
                
                if concavity > 0:
                    extrema.append((point_float, y_value, "Cực tiểu"))
                elif concavity < 0:
                    extrema.append((point_float, y_value, "Cực đại"))
            except:
                continue
    
    return extrema

def generate_plot(expression: str, show_asymptotes: bool = False, show_derivative: bool = False, show_extrema: bool = False):
    """
    Tạo đồ thị của hàm số và đạo hàm của nó, hỗ trợ cả phân thức và không phải phân thức.
    
    Args:
        expression (str): Biểu thức hàm số
        show_asymptotes (bool): Có hiển thị đường tiệm cận hay không
        show_derivative (bool): Có hiển thị đồ thị đạo hàm hay không
        show_extrema (bool): Có hiển thị điểm cựu trị hay không
    """
    try:
        expression = sanitize_input(expression)
        x = sp.Symbol('x')
        expr = sp.sympify(expression)
        
        # Tách biểu thức thành tử số và mẫu số
        numerator, denominator = extract_expression_parts(expr)
        
        # Xác định xem có phải là phân thức hay không
        is_rational = is_rational_function(expr)
        
        # Tính đạo hàm
        if show_derivative:
            derivative = calculate_derivative(expr)
        
        # Tìm tiệm cận
        vertical_asymptotes = find_vertical_asymptotes(denominator)
        horizontal_asymptote = calculate_horizontal_asymptote(numerator, denominator)
        
        # Tìm điểm cực trị
        extrema_points = find_extrema(expr) if show_extrema else []
        
        fig, ax = plt.subplots()
        
        # Xác định khoảng x để vẽ
        if vertical_asymptotes:
            x_ranges = []
            vas = sorted(vertical_asymptotes)
            
            # Thêm khoảng trước tiệm cận đứng đầu tiên
            if vas[0] > -10:
                x_ranges.append(np.linspace(-10, vas[0] - 0.1, 200))
            
            # Thêm các khoảng giữa các tiệm cận đứng
            for i in range(len(vas) - 1):
                x_ranges.append(np.linspace(vas[i] + 0.1, vas[i+1] - 0.1, 200))
            
            # Thêm khoảng sau tiệm cận đứng cuối cùng
            if vas[-1] < 10:
                x_ranges.append(np.linspace(vas[-1] + 0.1, 10, 200))
        else:
            # Nếu không có tiệm cận đứng, sử dụng một khoảng liên tục
            x_ranges = [np.linspace(-10, 10, 1000)]
        
        # Vẽ hàm gốc
        expression_latex = r"$f(x) = " + sp.latex(expr) + r"$"
        
        for x_range in x_ranges:
            try:
                y_values = []
                for xi in x_range:
                    try:
                        y_val = float(expr.subs(x, xi))
                        y_values.append(y_val)
                    except:
                        y_values.append(np.nan)
                
                y_values = np.array(y_values)
                valid_points = ~np.isnan(y_values) & ~np.isinf(y_values)
                
                if any(valid_points):
                    ax.plot(x_range[valid_points], y_values[valid_points], 'b-', 
                            label=expression_latex if x_range is x_ranges[0] else "")
            except Exception as e:
                print(f"Error plotting function: {e}")
        
        # Vẽ đạo hàm nếu được yêu cầu
        if show_derivative:
            derivative_latex = r"$f'(x) = " + sp.latex(derivative) + r"$"
            
            for x_range in x_ranges:
                try:
                    y_derivative = []
                    for xi in x_range:
                        try:
                            y_val = float(derivative.subs(x, xi))
                            y_derivative.append(y_val)
                        except:
                            y_derivative.append(np.nan)
                    
                    y_derivative = np.array(y_derivative)
                    valid_points = ~np.isnan(y_derivative) & ~np.isinf(y_derivative)
                    
                    if any(valid_points):
                        ax.plot(x_range[valid_points], y_derivative[valid_points], 'r--', 
                                label=derivative_latex if x_range is x_ranges[0] else "")
                except Exception as e:
                    print(f"Error plotting derivative: {e}")
        
        # Thu thập tất cả các giá trị y hợp lệ để xác định giới hạn trục y
        all_y_values = []
        
        # Thu thập giá trị y từ hàm gốc
        for x_range in x_ranges:
            for xi in x_range:
                try:
                    y_val = float(expr.subs(x, xi))
                    if not np.isnan(y_val) and not np.isinf(y_val):
                        all_y_values.append(y_val)
                except:
                    pass
        
        # Thu thập giá trị y từ đạo hàm
        if show_derivative:
            for x_range in x_ranges:
                for xi in x_range:
                    try:
                        y_val = float(derivative.subs(x, xi))
                        if not np.isnan(y_val) and not np.isinf(y_val):
                            all_y_values.append(y_val)
                    except:
                        pass
        
        # Thêm giá trị y từ điểm cực trị
        if extrema_points:
            for _, y_val, _ in extrema_points:
                all_y_values.append(y_val)
        
        # Thêm giá trị tiệm cận ngang
        if horizontal_asymptote is not None:
            all_y_values.append(horizontal_asymptote)
        
        # Thiết lập giới hạn trục y dựa trên giá trị thu thập được
        if all_y_values:
            y_filtered = np.array(all_y_values)
            if len(y_filtered) > 0:
                # Sử dụng percentile để loại bỏ các giá trị cực đoan
                if len(y_filtered) > 10:
                    y_min = max(-50, np.percentile(y_filtered, 1))
                    y_max = min(50, np.percentile(y_filtered, 99))
                else:
                    y_min = max(-50, np.min(y_filtered))
                    y_max = min(50, np.max(y_filtered))
                
                # Thêm khoảng trống để đồ thị trông đẹp hơn
                margin = (y_max - y_min) * 0.1
                ax.set_ylim(y_min - margin, y_max + margin)
        
        # Vẽ tiệm cận nếu được yêu cầu
        if show_asymptotes:
            # Vẽ tiệm cận đứng
            for va in vertical_asymptotes:
                va_fraction = sp.Rational(va).limit_denominator()
                va_latex = f"x = {sp.latex(va_fraction)}"
                ax.axvline(x=va, color='r', linestyle='--', alpha=0.7, 
                          label=f"Tiệm cận đứng: {va_latex}")
            
            # Vẽ tiệm cận ngang
            if horizontal_asymptote is not None:
                ha_fraction = sp.Rational(horizontal_asymptote).limit_denominator()
                ha_latex = f"y = {sp.latex(ha_fraction)}"
                ax.axhline(y=horizontal_asymptote, color='g', linestyle='--', alpha=0.7, 
                          label=f"Tiệm cận ngang: {ha_latex}")
        
        # Vẽ điểm cực trị
        if show_extrema and extrema_points:
            for x_ext, y_ext, ext_type in extrema_points:
                ax.scatter(x_ext, y_ext, color='red', zorder=3, marker='x', s=50,
                          label=f"{ext_type} tại x={x_ext:.2f}, y={y_ext:.2f}")
        
        # Thiết lập tiêu đề và các thành phần khác của đồ thị
        title = r'Đồ thị của hàm số và đạo hàm' if show_derivative else r'Đồ thị của hàm số'
        title += f': {expression}'
        ax.set_title(title, pad=5, fontsize=12)
        
        ax.grid(True, alpha=0.3)
        ax.set_xlabel('x')
        ax.set_ylabel('y')
        ax.axhline(y=0, color='k', linestyle='-', linewidth=0.5)
        ax.axvline(x=0, color='k', linestyle='-', linewidth=0.5)
        
        # Hiển thị legend với kích thước phù hợp
        handles, labels = ax.get_legend_handles_labels()
        by_label = dict(zip(labels, handles))
        ax.legend(by_label.values(), by_label.keys(), loc='best', fontsize='small')
        
        plt.tight_layout()
        return save_plot()
    
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        error_message = f"Lỗi: {str(e)}\n{tb}"
        raise HTTPException(status_code=400, detail=error_message)

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

def process_image_with_text(image_path: str, text: str):
    """Xử lý hình ảnh và văn bản bằng OpenAI."""
    img_path = Path(image_path)
    if not img_path.exists():
        return "Lỗi: Đường dẫn hình ảnh không tồn tại."

    msg = ChatMessage(
        role=MessageRole.USER,
        blocks=[
            TextBlock(text=text),
            ImageBlock(path=img_path, image_mimetype="image/jpeg"),
        ],
    )

    response = Settings.llm.chat(messages=[msg]) 

    return response

def initialize_chatbot(chat_store, user_id=None):
    """Khởi tạo chatbot với cấu hình."""
    if user_id is None:
        user_id = "guest"
        
    # Tạo bộ nhớ chatbot và load dữ liệu
    memory = ChatMemoryBuffer.from_defaults(
        token_limit=3000, 
        chat_store=chat_store, 
        chat_store_key=str(user_id)
    )
    
    storage_context = StorageContext.from_defaults(persist_dir=INDEX_STORAGE)
    index = load_index_from_storage(storage_context, index_id="vector")
    query_engine = index.as_query_engine(similarity_top_k=2)

    image_tool = FunctionTool.from_defaults(
        fn=process_image_with_text,
        name="image_tool",
        description="Nhận văn bản và hình ảnh, phân tích nội dung của hình ảnh và từ đó đưa ra trả lời cho người dùng. KẾT QUẢ TỪ TOOL NÀY NÊN ĐƯỢC TRẢ LẠI NGUYÊN VẸN CHO NGƯỜI DÙNG."
    )

     
    plot_tool = FunctionTool.from_defaults(
        fn=lambda expression, show_asymptotes=True, show_derivative=False, show_extrema=True: generate_plot(
            expression, 
            show_asymptotes=show_asymptotes, 
            show_derivative=show_derivative,
            show_extrema=show_extrema
        ),
        name="generate_plot",
        description="Vẽ đồ thị của hàm số, chỉ 1 hình duy nhất. Tham số show_asymptotes để chọn có hiển thị đường tiệm cận hay không, show_derivative để chọn có hiển thị đạo hàm hay không, show_extrema để chọn có hiển thị điểm cực trị hay không."
        
    )
    query_tool = QueryEngineTool(
        query_engine=query_engine, 
        metadata=ToolMetadata(
            name="query",
            description="Cung cấp câu hỏi và đáp án môn toán."
        )
    )
    
    agent = OpenAIAgent.from_tools(
        tools=[plot_tool, image_tool], 
        memory=memory,
        system_prompt=CUSTORM_AGENT_SYSTEM_TEMPLATE,
        verbose=True
    )
    
    return agent


def chat_response(agent, prompt: str, session_id: int, db: Session):
    """Nhận prompt và trả về phản hồi từ AI, đồng thời lưu tin nhắn vào database."""
    if "image_tool(" in prompt:
        image_path = prompt.split("image_tool('")[1].split("'")[0]  # Lấy đường dẫn ảnh
        text = prompt.split("', '")[1][:-2]  # Lấy phần nội dung text
    else:
        image_path = "Null"
        text = prompt

    promptDB = f"image: {image_path}, text: {text}"

    user_message = ChatMessageDB(
        session_id=session_id,
        role="user",
        content=promptDB,
    )
    db.add(user_message)
    db.commit()

    """
    Bug: Gặp bug nếu gửi prompt mà không có hình ảnh thì hỏi lại cùng prompt đó có hình ảnh sẽ gặp bị output cụt ngủn
    Nhận định: Có thể liên quan đến memory
    Hướng fix: Sự tương tác giữa image_tool, agent và memory
    """
    
    ai_response = str(agent.chat(prompt)) 

    ai_message = ChatMessageDB(
        session_id=session_id,
        role="assistant",
        content=ai_response,
    )
    db.add(ai_message)
    db.commit()

    return ai_response
