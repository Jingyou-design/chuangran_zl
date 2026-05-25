"""
MinerU API 客户端服务。

使用文件上传模式：申请上传链接 → PUT 上传文件 → 轮询 batch 结果 → 下载 Markdown。
无需公网 URL，直接从本地上传文件到 MinerU。
所有 yield 的事件均为 SSE 兼容的 dict 格式，可直接推送给前端。
"""

import asyncio
import io
import os
import time
import zipfile
from pathlib import Path
from typing import AsyncGenerator

import requests
from dotenv import load_dotenv

load_dotenv()

MINERU_TOKEN = os.getenv("MINERU_TOKEN", "")
BASE_URL = "https://mineru.net/api/v4"
POLL_INTERVAL = 3  # 秒
DEFAULT_TIMEOUT = 300  # 5 分钟


def _auth_headers() -> dict:
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {MINERU_TOKEN}",
    }


class MinerUService:
    """MinerU API 异步服务，使用文件上传模式，yield SSE 格式事件。"""

    def __init__(self, token: str | None = None):
        self.token = token or MINERU_TOKEN
        if not self.token:
            raise ValueError("MINERU_TOKEN 未设置，请在 .env 中配置")

    async def upload_file(
        self, file_path: str, filename: str, model_version: str = "vlm"
    ) -> str:
        """申请上传链接并上传文件，返回 batch_id。

        流程：
        1. POST /api/v4/file-urls/batch 获取上传链接和 batch_id
        2. PUT 文件到上传链接
        3. 系统自动开始解析
        """
        # 1. 申请上传链接
        payload = {
            "files": [{"name": filename}],
            "model_version": model_version,
            "enable_formula": True,
            "enable_table": True,
            "language": "ch",
        }

        def _request_upload():
            return requests.post(
                f"{BASE_URL}/file-urls/batch",
                headers=_auth_headers(),
                json=payload,
                timeout=30,
            )

        res = await asyncio.to_thread(_request_upload)
        body = res.json()

        if body.get("code") != 0:
            raise RuntimeError(f"MinerU 申请上传失败: {body.get('msg', '未知错误')}")

        data = body["data"]
        batch_id = data["batch_id"]
        file_urls = data.get("file_urls", [])

        if not file_urls:
            raise RuntimeError("MinerU 未返回上传链接")

        upload_url = file_urls[0]

        # 2. PUT 上传文件（不设 Content-Type，直接传二进制）
        with open(file_path, "rb") as f:
            file_bytes = f.read()

        def _put_file():
            return requests.put(
                upload_url,
                data=file_bytes,
                headers={},  # 不设 Content-Type
                timeout=120,
            )

        put_res = await asyncio.to_thread(_put_file)
        if put_res.status_code not in (200, 201, 204):
            raise RuntimeError(f"MinerU 上传文件失败: HTTP {put_res.status_code}")

        return batch_id

    async def poll_batch(
        self, batch_id: str, timeout: int = DEFAULT_TIMEOUT, thread_id: str = ""
    ) -> AsyncGenerator[dict, None]:
        """轮询 batch 解析结果，yield 进度事件。

        使用 GET /api/v4/extract-results/batch/{batch_id} 查询。
        返回数据格式: data.extract_result = [{"file_name", "state", ...}]
        state 可能的值: pending / processing / done / failed
        """
        start = time.time()
        result_data = None

        try:
            while time.time() - start < timeout:
                def _get():
                    return requests.get(
                        f"{BASE_URL}/extract-results/batch/{batch_id}",
                        headers=_auth_headers(),
                        timeout=30,
                    )

                res = await asyncio.to_thread(_get)
                body = res.json()

                if body.get("code") != 0:
                    raise RuntimeError(f"MinerU 查询失败: {body.get('msg', '未知错误')}")

                data = body.get("data", {})
                # 字段名是 extract_result（不是 results）
                extract_results = data.get("extract_result", [])

                elapsed = int(time.time() - start)

                # 从 batch 结果中提取单个文件的状态
                if extract_results:
                    task = extract_results[0]
                    state = task.get("state", "unknown")
                else:
                    state = "pending"

                yield {
                    "type": "progress",
                    "name": "mineru",
                    "data": {
                        "state": state,
                        "elapsed": elapsed,
                    },
                }

                if state == "done":
                    result_data = extract_results[0] if extract_results else {}
                    break

                if state == "failed":
                    err = task.get("err_msg", "未知错误") if extract_results else "未知错误"
                    raise RuntimeError(f"MinerU 任务失败: {err}")

                # 等待下一次轮询，期间每秒发送心跳保持 SSE 连接
                for _ in range(POLL_INTERVAL):
                    yield {"type": "heartbeat"}
                    await asyncio.sleep(1)
            else:
                raise TimeoutError(f"MinerU 任务超时({timeout}s)")

        except (RuntimeError, TimeoutError) as e:
            yield {"type": "error", "name": "mineru", "data": {"message": str(e)}}
            return

        # 下载并提取 Markdown
        zip_url = result_data.get("full_zip_url", "") if result_data else ""
        md_url = result_data.get("md_url", "") if result_data else ""

        if not zip_url and not md_url:
            yield {
                "type": "error",
                "name": "mineru",
                "data": {"message": "任务完成但未返回下载链接"},
            }
            return

        try:
            save_dir = str(Path("files/mineru_output") / (thread_id or batch_id))
            md_content, md_path = await self._fetch_markdown(zip_url, md_url, save_dir)
        except Exception as e:
            yield {"type": "error", "name": "mineru", "data": {"message": f"下载失败: {e}"}}
            return

        yield {
            "type": "mineru_done",
            "name": "mineru",
            "data": {
                "markdown": md_content,
                "markdown_length": len(md_content),
                "file_path": md_path,
            },
        }

    async def _download_with_retry(
        self, url: str, timeout: int = 120, max_retries: int = 3
    ) -> requests.Response:
        """带重试的 HTTP 下载，应对 SSL/网络波动。"""
        last_err = None
        for attempt in range(max_retries):
            try:
                def _get():
                    return requests.get(url, timeout=timeout)
                res = await asyncio.to_thread(_get)
                res.raise_for_status()
                return res
            except Exception as e:
                last_err = e
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 * (attempt + 1))
        raise last_err

    async def _fetch_markdown(
        self, zip_url: str, md_url: str, output_dir: str
    ) -> tuple[str, str]:
        """从 ZIP 或直接 MD 链接获取 Markdown 内容。"""

        # 优先从 ZIP 提取（更完整，含图片等）
        if zip_url:
            res = await self._download_with_retry(zip_url, timeout=120)
            Path(output_dir).mkdir(parents=True, exist_ok=True)

            with zipfile.ZipFile(io.BytesIO(res.content)) as zf:
                names = zf.namelist()
                md_name = None
                for n in names:
                    if n.endswith("full.md"):
                        md_name = n
                        break
                if not md_name:
                    md_candidates = [n for n in names if n.endswith(".md")]
                    if md_candidates:
                        md_name = md_candidates[0]
                    else:
                        raise RuntimeError("MinerU 结果 ZIP 中未找到 Markdown 文件")

                md_content = zf.read(md_name).decode("utf-8")
                md_path = str(Path(output_dir) / Path(md_name).name)
                with open(md_path, "w", encoding="utf-8") as f:
                    f.write(md_content)

            return md_content, md_path

        # 降级：直接下载 MD
        if md_url:
            res = await self._download_with_retry(md_url, timeout=60)
            md_content = res.text

            Path(output_dir).mkdir(parents=True, exist_ok=True)
            md_path = str(Path(output_dir) / "full.md")
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(md_content)

            return md_content, md_path

        raise RuntimeError("无可用下载链接")

    async def process_file(
        self,
        file_path: str,
        filename: str,
        model_version: str = "vlm",
        timeout: int = DEFAULT_TIMEOUT,
        thread_id: str = "",
    ) -> AsyncGenerator[dict, None]:
        """端到端处理：申请上传 → PUT 文件 → 轮询进度 → 下载 Markdown。"""

        # 1. 申请上传链接 + 上传文件
        try:
            batch_id = await self.upload_file(file_path, filename, model_version)
        except Exception as e:
            yield {"type": "error", "name": "mineru", "data": {"message": str(e)}}
            return

        # 2. 轮询 batch 结果 + 下载
        async for event in self.poll_batch(batch_id, timeout, thread_id=thread_id):
            yield event
