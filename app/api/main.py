from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.api.routes import stream

STATIC_DIR = Path(__file__).parent / "static"
FILES_DIR = Path(__file__).resolve().parent.parent.parent / "files"

def create_app() -> FastAPI:
    app = FastAPI(
        title="专利方案生成与评估系统",
        description="基于 LangGraph + astream_events 的流式专利方案生成 API",
        version="0.1.0",
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
