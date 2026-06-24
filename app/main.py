from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os

from app.api.auth import router as auth_router # 💡 인증 라우터 추가
from app.api.board import router as board_router
from app.api.board_db import init_board_db
from app.api.merchants import router as merchants_router
from app.api.history import router as history_router
from app.api.sync import router as sync_router, run_mdb_sync
from app.api.cute_animals import router as cute_animal_router
from app.api.version import router as version_router
from app.version import APP_VERSION


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_board_db()
    run_mdb_sync()
    yield


app = FastAPI(
    title="보안 가맹점 마스터 및 이력 관리 시스템",
    version="1.0.002",
    lifespan=lifespan,
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
app.include_router(cute_animal_router)
app.include_router(version_router)
app.include_router(board_router)

current_dir = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(current_dir, "static")), name="static")

@app.get("/")
def read_index():
    return FileResponse(os.path.join(current_dir, "index.html"))


@app.get("/board")
def read_board():
    return FileResponse(os.path.join(current_dir, "board.html"))


@app.get("/api/health")
def health_check():
    return {"status": "ok", "version": APP_VERSION}
