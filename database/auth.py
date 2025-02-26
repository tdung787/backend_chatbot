from passlib.context import CryptContext
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
from database.models import ActiveToken
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from database.db import get_db

SECRET_KEY = "mysecretkey"  # Thay đổi thành một chuỗi bí mật mạnh hơn
ALGORITHM = "HS256"

# Tạo context để hash mật khẩu
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Cấu hình bảo mật OAuth2 (Bearer Token)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

# Hash mật khẩu
def hash_password(password: str) -> str:
    return pwd_context.hash(password)

# Kiểm tra mật khẩu
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

# Tạo JWT token
def create_access_token(data: dict, db: Session, expires_delta: int = 1440):
    to_encode = data.copy()

    # Đảm bảo user_id (sub) luôn là string
    if "sub" in to_encode:
        to_encode["sub"] = str(to_encode["sub"])

    expire = datetime.now(timezone.utc) + timedelta(minutes=expires_delta)
    to_encode.update({"exp": expire})

    # Lặp lại cho đến khi tạo được token mới
    for _ in range(5):  # Giới hạn tối đa 5 lần thử
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

        # Kiểm tra xem token đã tồn tại trong DB chưa
        existing_token = db.query(ActiveToken).filter_by(token=encoded_jwt).first()
        if not existing_token:
            break  # Token chưa tồn tại, có thể lưu vào DB
    else:
        raise Exception("Không thể tạo token duy nhất sau nhiều lần thử.")

    # Lưu token vào database
    db_token = ActiveToken(token=encoded_jwt, user_id=data["sub"], expires_at=expire)
    db.add(db_token)
    db.commit()

    return encoded_jwt

def verify_token(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(
            token, 
            SECRET_KEY, 
            algorithms=[ALGORITHM],
        )
        
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=401, 
                detail="Token thiếu thông tin người dùng"
            )
            
        try:
            user_id = int(str(user_id).strip())
        except ValueError:
            raise HTTPException(
                status_code=401, 
                detail="ID người dùng không hợp lệ"
            )
        
        # Kiểm tra token trong bảng ActiveToken
        db_token = db.query(ActiveToken).filter(
            ActiveToken.token == token,
            ActiveToken.user_id == user_id
        ).first()
        
        if not db_token:
            raise HTTPException(
                status_code=401,
                detail="Token không còn hiệu lực"
            )
            
        return {
            "user_id": payload.get("sub"),
            "ho_va_ten": payload.get("ho_va_ten"),
            "noi_o": payload.get("noi_o")
        }

    except JWTError:
        raise HTTPException(
            status_code=401,
            detail="Token không hợp lệ"
        )
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Lỗi server trong quá trình xác thực"
        )