from passlib.context import CryptContext
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
from database.models import ActiveToken
import jwt
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from database.db import get_db
from database.models import User
import logging

SECRET_KEY = "mysecretkey"  # Thay đổi thành một chuỗi bí mật mạnh hơn
ALGORITHM = "HS256"

# Cấu hình logger
logging.basicConfig(
    level=logging.DEBUG,  # Có thể điều chỉnh level: DEBUG, INFO, WARNING, ERROR, CRITICAL
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),  # Lưu log vào file
        logging.StreamHandler()  # Hiển thị log trên console
    ]
)

# Tạo logger cho module của bạn
logger = logging.getLogger(__name__)
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
        # Thêm logging để dễ debug
        logger.debug(f"Verifying token: {token[:100]}...")  # Chỉ log 10 ký tự đầu của token
         
        # Log kiểu dữ liệu của các tham số truyền vào jwt.decode
        logger.debug(f"Type of token: {type(token)}")
        logger.debug(f"Type of SECRET_KEY: {type(SECRET_KEY)}")
        logger.debug(f"Type of ALGORITHM: {type(ALGORITHM)}")
        
        # Giải mã token với các options cụ thể hơn
        payload = jwt.decode(
            token, 
            SECRET_KEY, 
            algorithms=[ALGORITHM],
         
        )
        # Log payload để debug (remove trong production)
        logger.debug(f"Token payload: {payload}")
        
        # Kiểm tra sub tồn tại và là string hợp lệ
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=401, 
                detail="Token thiếu thông tin người dùng"
            )
            
        # Chuyển user_id về integer an toàn hơn
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
            ActiveToken.user_id == user_id  # Thêm điều kiện này
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

    except JWTError as e:
        logger.error(f"JWT verification failed: {str(e)}")
        raise HTTPException(
            status_code=401,
            detail="Token không hợp lệ"
        )
    except Exception as e:
        logger.error(f"Unexpected error in verify_token: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Lỗi server trong quá trình xác thực"
        )



