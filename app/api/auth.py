from __future__ import annotations

import datetime
import hashlib
import json
import os
from pathlib import Path

import jwt
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

ADMIN_AUTH_PATH = Path(os.getenv("ADMIN_AUTH_PATH", "/data/admin_auth.json"))


class Settings(BaseSettings):
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin1234!"
    SECRET_KEY: str = "vcall_default_secret_fallback_key"
    ACCESS_TOKEN_EXPIRE_DAYS: int = 7


settings = Settings()
ALGORITHM = "HS256"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

_credentials: dict[str, str] = {"username": "", "password_hash": ""}


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def _save_credentials(username: str, password_hash: str) -> None:
    ADMIN_AUTH_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {"username": username, "password_hash": password_hash}
    temp_path = ADMIN_AUTH_PATH.with_suffix(".tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(ADMIN_AUTH_PATH)
    try:
        os.chmod(ADMIN_AUTH_PATH, 0o600)
    except OSError:
        pass


def load_credentials() -> None:
    if ADMIN_AUTH_PATH.exists():
        try:
            data = json.loads(ADMIN_AUTH_PATH.read_text(encoding="utf-8"))
            username = (data.get("username") or "").strip()
            password_hash = (data.get("password_hash") or "").strip()
            if username and password_hash:
                _credentials["username"] = username
                _credentials["password_hash"] = password_hash
                return
        except (json.JSONDecodeError, OSError):
            pass

    username = settings.ADMIN_USERNAME.strip()
    password_hash = hash_password(settings.ADMIN_PASSWORD)
    _credentials["username"] = username
    _credentials["password_hash"] = password_hash
    _save_credentials(username, password_hash)


def get_admin_username() -> str:
    if not _credentials["username"]:
        load_credentials()
    return _credentials["username"]


def verify_password(password: str) -> bool:
    if not _credentials["password_hash"]:
        load_credentials()
    return hash_password(password) == _credentials["password_hash"]


load_credentials()


class LoginRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8, max_length=128)


def _decode_access_token(token: str) -> str:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="로그인이 필요하거나 인증 토큰이 만료되었습니다.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None or username != get_admin_username():
            raise credentials_exception
        return username
    except jwt.PyJWTError:
        raise credentials_exception


def get_current_user(token: str = Depends(oauth2_scheme)):
    return _decode_access_token(token)


def get_current_user_for_media(
    authorization: str | None = Header(None),
    token: str | None = Query(None),
):
    raw_token = None
    if authorization and authorization.lower().startswith("bearer "):
        raw_token = authorization[7:].strip()
    elif token:
        raw_token = token.strip()
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="로그인이 필요하거나 인증 토큰이 만료되었습니다.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _decode_access_token(raw_token)


@router.post("/login")
def login(data: LoginRequest):
    if data.username != get_admin_username() or not verify_password(data.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="아이디 또는 비밀번호가 일치하지 않습니다.",
        )

    expire = datetime.datetime.utcnow() + datetime.timedelta(days=settings.ACCESS_TOKEN_EXPIRE_DAYS)
    to_encode = {"sub": data.username, "exp": expire}
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)

    return {
        "access_token": encoded_jwt,
        "token_type": "bearer",
        "username": data.username,
    }


@router.post("/change-password")
def change_password(payload: ChangePasswordRequest, current_user: str = Depends(get_current_user)):
    if not verify_password(payload.current_password):
        raise HTTPException(status_code=400, detail="현재 비밀번호가 일치하지 않습니다.")
    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=400, detail="새 비밀번호는 현재 비밀번호와 달라야 합니다.")

    new_hash = hash_password(payload.new_password)
    _credentials["password_hash"] = new_hash
    _save_credentials(current_user, new_hash)
    return {"ok": True, "message": "비밀번호가 변경되었습니다."}
