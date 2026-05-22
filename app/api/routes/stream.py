"""
FastAPI 流式路由。
提供 /api/v1/stream/start、/resume、/upload、/parse 等 SSE 端点。
"""

import json
import shutil
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.controller_stream.session_stream import stream_session, resume_session, resume_session_with_text
from app.services.mineru_service import MinerUService


router = APIRouter(prefix="/api/v1/stream", tags=["stream"])

# ---------- 配置 ----------

UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent.parent / "files"
ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx", ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

# MinerU 服务实例
_mineru = MinerUService()


# ---------- 请求模型 ----------

class StartRequest(BaseModel):
    document: str
    thread_id: Optional[str] = None


class ResumeRequest(BaseModel):
    thread_id: str
    intent: str
    feedback: Optional[str] = ""


class ResumeTextRequest(BaseModel):
    thread_id: str
    user_input: str


class ParseRequest(BaseModel):
    thread_id: str
    file_path: str
    filename: str
    model_version: Optional[str] = "vlm"


class CleanupRequest(BaseModel):
    thread_id: str


# ---------- SSE 辅助 ----------

async def _sse_generator(session_gen):
    """将 session_stream 的 dict payload 包装为 SSE 格式。"""
    try:
        async for payload in session_gen:
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
    except Exception as e:
        error_payload = {"type": "error", "name": "", "data": {"message": str(e)}}
        yield f"data: {json.dumps(error_payload, ensure_ascii=False)}\n\n"


# ---------- 文件上传端点 ----------

@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """上传文件到服务器，返回 thread_id 和 file_path 供 MinerU 文件上传模式使用。"""

    # 校验扩展名
    filename = Path(file.filename).name  # 防路径穿越
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型: {ext}，支持: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    # 生成 thread_id 和保存目录
    thread_id = f"stream-{uuid.uuid4().hex[:12]}"
    save_dir = UPLOAD_DIR / thread_id
    save_dir.mkdir(parents=True, exist_ok=True)

    save_path = save_dir / filename

    # 写入文件（流式，避免大文件占内存）
    file_size = 0
    with open(save_path, "wb") as f:
        while True:
            chunk = await file.read(1024 * 1024)  # 1MB chunks
            if not chunk:
                break
            file_size += len(chunk)
            if file_size > MAX_FILE_SIZE:
                # 超限则删除已写入的文件
                save_path.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="文件大小超过 50MB 限制")
            f.write(chunk)

    # 构造返回信息（file_path 用于后端 /parse 直接传给 MinerU）
    file_path = str(save_path)

    return {
        "thread_id": thread_id,
        "filename": filename,
        "file_path": file_path,
        "file_size": file_size,
    }


# ---------- MinerU 解析端点 ----------

@router.post("/parse")
async def parse_file(req: ParseRequest):
    """提交文件到 MinerU 进行 Markdown 转换，以 SSE 返回进度和结果。

    SSE 事件类型：
    - progress: MinerU 解析进度
    - mineru_done: 解析完成，data 中包含 markdown 字段
    - error: 解析失败
    """

    async def gen():
        async for payload in _mineru.process_file(
            file_path=req.file_path,
            filename=req.filename,
            model_version=req.model_version or "vlm",
        ):
            if payload.get("type") == "heartbeat":
                yield ": keepalive\n\n"
            else:
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------- 原有端点 ----------

@router.post("/start")
async def start_stream(req: StartRequest):
    """启动专利方案生成会话，以 SSE 形式流式返回事件。"""
    thread_id = req.thread_id or f"stream-{uuid.uuid4().hex[:12]}"

    async def gen():
        yield f"data: {json.dumps({'type': 'meta', 'name': 'thread_id', 'data': {'thread_id': thread_id}}, ensure_ascii=False)}\n\n"
        async for chunk in _sse_generator(stream_session(req.document, thread_id)):
            yield chunk

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/resume")
async def resume_stream(req: ResumeRequest):
    """恢复被 interrupt 暂停的会话。"""
    if not req.thread_id:
        raise HTTPException(status_code=400, detail="thread_id is required")

    decision = {"intent": req.intent, "feedback": req.feedback or ""}

    return StreamingResponse(
        _sse_generator(resume_session(req.thread_id, decision)),
        media_type="text/event-stream",
    )


@router.post("/resume-text")
async def resume_stream_text(req: ResumeTextRequest):
    """恢复会话（自然语言版本）。"""
    if not req.thread_id:
        raise HTTPException(status_code=400, detail="thread_id is required")

    return StreamingResponse(
        _sse_generator(resume_session_with_text(req.thread_id, req.user_input)),
        media_type="text/event-stream",
    )


# ---------- 清理端点 ----------

@router.post("/cleanup")
async def cleanup_session(req: CleanupRequest):
    """清理会话：删除上传的文件目录。"""
    thread_id = req.thread_id
    # 只允许删除 files/stream-xxx 格式的目录，防止路径穿越
    if not thread_id.startswith("stream-"):
        raise HTTPException(status_code=400, detail="无效的 thread_id")

    session_dir = UPLOAD_DIR / thread_id
    deleted = False
    if session_dir.is_dir():
        shutil.rmtree(session_dir, ignore_errors=True)
        deleted = True

    return {"thread_id": thread_id, "deleted": deleted}
