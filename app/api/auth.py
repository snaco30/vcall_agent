from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic_settings import BaseSettings
from pydantic import BaseModel
import jwt
import datetime
import hashlib
import os

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

# 💡 [경로 간섭 해결]: 파일 기반 로딩을 배제하고, 도커가 주입한 시스템 환경 변수를 우선적으로 바로 긁어옵니다.
class Settings(BaseSettings):
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin1234!"
    SECRET_KEY: str = "vcall_default_secret_fallback_key"
    ACCESS_TOKEN_EXPIRE_HOURS: int = 8

# 환경 변수 가동
settings = Settings()

ALGORITHM = "HS256"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

# .env에서 전달받은 마스터 계정 해시 매핑
ADMIN_USERNAME_TARGET = settings.ADMIN_USERNAME
ADMIN_PASSWORD_HASH = hash_password(settings.ADMIN_PASSWORD)

class LoginRequest(BaseModel):
    username: str
    password: str

def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="로그인이 필요하거나 인증 토큰이 만료되었습니다.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None or username != ADMIN_USERNAME_TARGET:
            raise credentials_exception
        return username
    except jwt.PyJWTError:
        raise credentials_exception

@router.post("/login")
def login(data: LoginRequest):
    if data.username != ADMIN_USERNAME_TARGET or hash_password(data.password) != ADMIN_PASSWORD_HASH:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="아이디 또는 비밀번호가 일치하지 않습니다."
        )
    
    expire = datetime.datetime.utcnow() + datetime.timedelta(hours=settings.ACCESS_TOKEN_EXPIRE_HOURS)
    to_encode = {"sub": data.username, "exp": expire}
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
    
    return {
        "access_token": encoded_jwt,
        "token_type": "bearer",
        "username": data.username
    }