from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import os

from app.api.auth import router as auth_router # 💡 인증 라우터 추가
from app.api.merchants import router as merchants_router
from app.api.history import router as history_router
from app.api.sync import router as sync_router

app = FastAPI(
    title="보안 가맹점 마스터 및 이력 관리 시스템",
    version="2.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(auth_router)
app.include_router(merchants_router)
app.include_router(history_router)
app.include_router(sync_router)

@app.get("/")
def read_index():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    return FileResponse(os.path.join(current_dir, "index.html"))