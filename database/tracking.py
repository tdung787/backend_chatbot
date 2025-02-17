import json
import os
from datetime import datetime
from pathlib import Path
from database.models import ActiveToken

def update_tracking_data(db):
    # Tạo thư mục data nếu chưa tồn tại
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)
    
    json_path = data_dir / "tracking.json"
    
    # Đọc dữ liệu hiện tại hoặc tạo mới nếu file chưa tồn tại
    if json_path.exists():
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    else:
        data = {
            "Active_user": 0,
            "Total_visit": 0
        }
    
    # Đếm số lượng token active hiện tại
    active_tokens_count = db.query(ActiveToken).filter(
        ActiveToken.expires_at > datetime.utcnow()
    ).count()
    
    # Cập nhật dữ liệu
    data["Active_user"] = active_tokens_count
    data["Total_visit"] += 1
    
    # Lưu dữ liệu vào file
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)
    
    return data
