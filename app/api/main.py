"""
FastAPI 应用入口。
挂载前端静态页面，启动时自动打开浏览器。
"""

import asyncio
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.api.routes import stream


STATIC_DIR = Path(__file__).parent / "static"
FILES_DIR = Path(__file__).resolve().parent.parent.parent / "files"


# 标记是否已打开过浏览器（避免 --reload 重载时重复打开）
_browser_opened = False


async def _open_browser_delayed():
    """延迟打开浏览器，仅在首次启动时执行。"""
    global _browser_opened
    if _browser_opened:
        return
    _browser_opened = True
    await asyncio.sleep(1.5)
    try:
        webbrowser.open("http://127.0.0.1:8000/")
    except Exception:
        pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动完成后自动打开浏览器。"""
    asyncio.create_task(_open_browser_delayed())
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="专利方案生成与评估系统",
        description="基于 LangGraph + astream_events 的流式专利方案生成 API",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 挂载静态文件
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    # 根路径返回前端页面
    @app.get("/")
    async def index():
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    app.include_router(stream.router)

    # 挂载上传文件目录（供 MinerU 访问），放在路由之后避免覆盖
    FILES_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/files", StaticFiles(directory=FILES_DIR), name="files")

    return app


app = create_app()
