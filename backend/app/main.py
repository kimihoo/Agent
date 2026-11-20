"""企业 AI 知识库助手 - 应用入口。"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import BASE_DIR
from .db import engine
from .models import Base
from .routers import admin, auth, chat, contracts, kb
from .seed import seed

app = FastAPI(title="企业 AI 知识库助手", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(kb.router)
app.include_router(chat.router)
app.include_router(contracts.router)
app.include_router(admin.router)

FRONTEND_DIST = BASE_DIR.parent / "frontend" / "dist"


@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(bind=engine)
    seed()


@app.get("/api/health")
def health():
    return {"status": "ok"}


if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")


@app.get("/{full_path:path}")
def serve_spa(full_path: str):
    if full_path.startswith("api/"):
        raise HTTPException(404, "Not Found")
    index = FRONTEND_DIST / "index.html"
    if index.exists():
        return FileResponse(index)
    return {
        "message": "前端尚未构建。开发模式请运行 cd frontend && npm run dev；"
                   "或将构建产物放到 frontend/dist 后重启服务。"
    }
