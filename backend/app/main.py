"""应用入口。

后端同时托管前端构建产物（frontend/dist），
生产/公网场景只需暴露一个端口（8000），前端后端同源，无跨域问题。
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api.routes import router
from .core.config import settings
from .models.db import init_db

app = FastAPI(title="AI 私教学习系统", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.on_event("startup")
async def startup():
    init_db()


# ---------- 托管前端构建产物 ----------
FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"

if FRONTEND_DIST.exists():
    # 静态资源（js/css/图片等）
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")


@app.get("/{full_path:path}", include_in_schema=False)
async def spa_fallback(full_path: str):
    """SPA 回退：静态文件原样返回，其余交给前端路由。"""
    if full_path.startswith("api/") or full_path.startswith("docs") or full_path.startswith("openapi"):
        from fastapi import HTTPException
        raise HTTPException(404)
    if FRONTEND_DIST.exists() and full_path:
        candidate = (FRONTEND_DIST / full_path).resolve()
        try:
            candidate.relative_to(FRONTEND_DIST.resolve())
        except ValueError:
            from fastapi import HTTPException
            raise HTTPException(404)
        if candidate.is_file():
            return FileResponse(candidate)
    index = FRONTEND_DIST / "index.html"
    if index.exists():
        return FileResponse(index)
    return {"message": "前端未构建，请先运行 npm run build"}
