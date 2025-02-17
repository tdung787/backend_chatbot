from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from fastapi.security import OAuth2PasswordBearer
from database.db import get_db
from database.models import User, ActiveToken
from database.auth import hash_password


router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

class UserCreate(BaseModel):
    ho_va_ten: str
    sdt: str
    email: EmailStr
    facebook: str | None = None 
    noi_o: str
    ten_truong: str
    password: str


#Register API
@router.post("/register")
def register_user(user: UserCreate, db: Session = Depends(get_db)):
    # Kiểm tra số điện thoại đã tồn tại chưa
    if db.query(User).filter(User.sdt == user.sdt).first():
        raise HTTPException(status_code=400, detail="Số điện thoại đã tồn tại")

    # Kiểm tra email đã tồn tại chưa
    if db.query(User).filter(User.email == user.email).first():
        raise HTTPException(status_code=400, detail="Email đã tồn tại")

    # Băm mật khẩu
    hashed_password = hash_password(user.password)

    # Tạo người dùng mới
    new_user = User(
        ho_va_ten=user.ho_va_ten,
        sdt=user.sdt,
        email=user.email,
        facebook=user.facebook,
        noi_o=user.noi_o,
        ten_truong=user.ten_truong,
        hashed_password=hashed_password
    )
    
    # Lưu vào database
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # Trả về tất cả thông tin trừ mật khẩu
    return {
        "message": "Đăng ký thành công",
        "user": {
            "id": new_user.id,
            "ho_va_ten": new_user.ho_va_ten,
            "sdt": new_user.sdt,
            "email": new_user.email,
            "facebook": new_user.facebook,
            "noi_o": new_user.noi_o,
            "ten_truong": new_user.ten_truong,
        }
    }



#Logout API
@router.post("/logout")
def logout(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    db_token = db.query(ActiveToken).filter(ActiveToken.token == token).first()
    if db_token:
        db.delete(db_token)
        db.commit()
        return {"message": "Đăng xuất thành công"}

    raise HTTPException(status_code=400, detail="Token không hợp lệ hoặc đã bị xóa trước đó")
