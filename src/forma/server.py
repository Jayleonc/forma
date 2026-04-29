"""Async callback-driven FastAPI server for forma."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import queue as _queue_module
import sys
import tempfile
import threading
import time
import uuid
from functools import partial
from multiprocessing import Process, Queue as MPQueue
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
from fastapi import FastAPI, status, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, AnyHttpUrl, ConfigDict, Field
import contextlib

from .conversion.workflow import run_conversion, run_fallback, VLM_SUPPORTED_SUFFIXES
from .shared.custom_types import Strategy

# ============================================================================
# Logging Configuration
# ============================================================================
# Configure logging before any logger is created
# This ensures all module loggers inherit the correct level and format
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)

# Set root logger level explicitly to ensure propagation
logging.getLogger().setLevel(LOG_LEVEL)

logger = logging.getLogger(__name__)
logger.info("Logging initialized with level: %s", LOG_LEVEL)

# ============================================================================
# Configuration
# ============================================================================
CONVERSION_TIMEOUT = float(os.getenv("FORMA_CONVERSION_TIMEOUT", "600"))
QA_TIMEOUT = float(os.getenv("FORMA_QA_TIMEOUT", "600"))
FALLBACK_TIMEOUT = float(os.getenv("FORMA_FALLBACK_TIMEOUT", "300"))
DATA_DIR = Path(os.getenv("FORMA_DATA_DIR", "./data"))
CONVERSION_WORKERS = int(os.getenv("CONVERSION_WORKERS", "4"))
QA_WORKERS = int(os.getenv("QA_WORKERS", "2"))
CALLBACK_TOKEN = os.getenv("CALLBACK_TOKEN", "forma-secret-2024")
MAX_INLINE_MD_BYTES = int(os.getenv("FORMA_MAX_INLINE_MD_BYTES", str(2 * 1024 * 1024)))
MIN_CALLBACK_DELAY_MS = int(os.getenv("FORMA_MIN_CALLBACK_DELAY_MS", "500"))
MAX_QUEUE_SIZE = int(os.getenv("FORMA_MAX_QUEUE_SIZE", "1000"))
QUEUE_PUT_TIMEOUT = float(os.getenv("FORMA_QUEUE_PUT_TIMEOUT", "5.0"))

logger.info("Configuration loaded:")
logger.info("  - CONVERSION_TIMEOUT: %s seconds", CONVERSION_TIMEOUT)
logger.info("  - QA_TIMEOUT: %s seconds", QA_TIMEOUT)
logger.info("  - FALLBACK_TIMEOUT: %s seconds", FALLBACK_TIMEOUT)
logger.info("  - DATA_DIR: %s", DATA_DIR)
logger.info("  - CONVERSION_WORKERS: %s", CONVERSION_WORKERS)
logger.info("  - QA_WORKERS: %s", QA_WORKERS)
logger.info("  - CALLBACK_TOKEN configured: %s", bool(CALLBACK_TOKEN))
logger.info("  - MAX_INLINE_MD_BYTES: %s bytes", MAX_INLINE_MD_BYTES)
logger.info("  - MIN_CALLBACK_DELAY_MS: %s ms", MIN_CALLBACK_DELAY_MS)
logger.info("  - MAX_QUEUE_SIZE: %s", MAX_QUEUE_SIZE)
logger.info("  - QUEUE_PUT_TIMEOUT: %s seconds", QUEUE_PUT_TIMEOUT)

class ConvertRequest(BaseModel):
    # Canonicalize to request_id as external and internal name
    model_config = ConfigDict(populate_by_name=True)

    request_id: str
    document_id: str | None = None
    source_url: AnyHttpUrl
    callback_url: AnyHttpUrl
    asset_upload_url: AnyHttpUrl | None = None
    asset_upload_token: str | None = None


class ConvertResponse(BaseModel):
    task_id: str
    status: str = "processing"


# 定义回调 payload
class CallbackPayload(BaseModel):
    # 使用下划线风格的字段名
    model_config = ConfigDict(populate_by_name=True)

    request_id: str
    status: str
    markdown_content: str | None = None
    error_message: str | None = None
    visual_facts: list[dict[str, object]] | None = None


class KnowledgeHubCallbackPayload(BaseModel):
    """Knowledge Hub specific callback payload."""

    model_config = ConfigDict(populate_by_name=True)

    request_id: str = Field(..., description="Knowledge Hub task ID")
    status: str = Field(..., description="completed or failed")
    markdown: str | None = Field(None, description="Markdown content on success")
    visual_facts: list[dict[str, object]] | None = Field(None, description="Optional visual facts")
    error: str | None = Field(None, description="Error message on failure")


# 定义一个任务类，用于存储任务信息
class ConversionTask(BaseModel):
    task_id: str
    request_id: str
    document_id: str | None = None
    source_url: AnyHttpUrl | None = None
    callback_url: AnyHttpUrl
    inline_markdown: str | None = None
    asset_upload_url: AnyHttpUrl | None = None
    asset_upload_token: str | None = None


# 新增 FAQ 生成相关模型
class GenerateQARequest(BaseModel):
    # 与 ConvertRequest 保持一致的命名规范
    model_config = ConfigDict(populate_by_name=True)

    request_id: str
    callback_url: AnyHttpUrl
    markdown_content: str  # 直接接收文本内容，而不是文件 URL


class GenerateQAResponse(BaseModel):
    # 与 ConvertResponse 保持一致的结构
    task_id: str
    status: str = "processing"


class QACallbackPayload(BaseModel):
    # 与 CallbackPayload 保持一致的命名规范
    model_config = ConfigDict(populate_by_name=True)

    request_id: str
    status: str
    faq_json: str | None = None  # JSON 字符串，内容是对象而非数组
    error_message: str | None = None


class GenerateQATask(BaseModel):
    # 与 ConversionTask 保持一致的结构
    task_id: str
    request_id: str
    markdown_content: str
    callback_url: AnyHttpUrl


class ConvertByContentRequest(BaseModel):
    """Request model for convert-by-content endpoint."""

    model_config = ConfigDict(populate_by_name=True)

    request_id: str = Field(..., description="Request ID for idempotency and correlation")
    document_id: str | None = Field(default=None, description="Knowledge Hub document ID used for asset binding")
    markdown_content: str = Field(..., description="Markdown content to process")
    callback_url: AnyHttpUrl = Field(..., description="Callback URL for results")
    content_type: str = Field(default="text/markdown", description="Content type")
    strategy: Strategy = Field(default=Strategy.AUTO, description="Processing strategy")
    asset_upload_url: AnyHttpUrl | None = Field(default=None, description="Knowledge Hub internal asset upload endpoint")
    asset_upload_token: str | None = Field(default=None, description="Knowledge Hub internal asset upload token")


app = FastAPI()
# 定义两个队列，一个用于处理文档转换任务，一个用于处理 FAQ 生成任务
# 全局对象
conversion_queue: asyncio.Queue[ConversionTask] = asyncio.Queue(maxsize=MAX_QUEUE_SIZE)
qa_queue: asyncio.Queue[GenerateQATask] = asyncio.Queue(maxsize=MAX_QUEUE_SIZE)


# ============================================================================
# 进程隔离工具 — 替代 asyncio.to_thread 解决线程泄漏问题
# ============================================================================
# 专用于等待子进程 IPC 结果的轻量线程池（仅做 Queue.get 阻塞等待，不执行 CPU 密集操作）
import concurrent.futures as _cf
_ipc_thread_pool = _cf.ThreadPoolExecutor(max_workers=8, thread_name_prefix="ipc-waiter")


def _subprocess_entry(func, result_queue):
    """子进程入口：执行 func 并将结果放入队列。"""
    try:
        result = func()
        result_queue.put(("ok", result))
    except Exception as e:
        # 异常对象可能不可跨进程序列化，转为字符串保证安全
        result_queue.put(("error", f"{e.__class__.__name__}: {e}"))


def _poll_queue(q, stop_event, poll_interval=0.5):
    """短轮询等待队列结果。stop_event 置位时快速退出，避免线程泄漏。"""
    while not stop_event.is_set():
        try:
            return q.get(timeout=poll_interval)
        except _queue_module.Empty:
            continue
    raise RuntimeError("poll stopped by stop_event")


async def run_in_subprocess(func, *, timeout=None):
    """在独立子进程中执行同步函数，超时后可通过 kill 彻底回收。

    解决 asyncio.to_thread 的两大缺陷：
    1. 共享默认线程池 → 独立子进程，完全隔离
    2. 超时后线程不可取消 → 子进程 kill 连带回收所有资源（含嵌套线程）
    """
    result_queue = MPQueue()
    stop_event = threading.Event()
    process = Process(target=_subprocess_entry, args=(func, result_queue), daemon=True)
    process.start()
    logger.debug("子进程已启动 PID=%s", process.pid)

    loop = asyncio.get_running_loop()

    try:
        status, payload = await asyncio.wait_for(
            loop.run_in_executor(
                _ipc_thread_pool,
                partial(_poll_queue, result_queue, stop_event),
            ),
            timeout=timeout,
        )

        if status == "ok":
            return payload
        else:
            raise RuntimeError(payload)
    except asyncio.TimeoutError:
        logger.warning("子进程 PID=%s 超时 (%.0fs)，正在 kill...", process.pid, timeout or 0)
        stop_event.set()
        process.kill()
        process.join(timeout=5)
        if process.is_alive():
            logger.error("子进程 PID=%s kill 后仍存活！", process.pid)
        raise
    finally:
        stop_event.set()  # 确保轮询线程退出
        if process.is_alive():
            process.terminate()
            process.join(timeout=3)
        try:
            result_queue.close()
            result_queue.join_thread()
        except Exception:
            pass


# ============================================================================
# 可观测性指标
# ============================================================================
class ConversionMetrics:
    """转换任务可观测性指标（线程安全）。"""

    def __init__(self):
        self._lock = threading.Lock()
        self.total_conversions = 0
        self.total_qa = 0
        self.total_fallbacks = 0
        self.fallback_successes = 0
        self.fallback_failures = 0
        self.fallback_timeouts = 0
        self.fallback_type_rejections = 0
        self.total_fallback_duration_s = 0.0

    def record_conversion(self):
        with self._lock:
            self.total_conversions += 1

    def record_qa(self):
        with self._lock:
            self.total_qa += 1

    def record_fallback(self, *, success: bool, duration: float,
                        timed_out: bool = False, type_rejected: bool = False):
        with self._lock:
            self.total_fallbacks += 1
            if type_rejected:
                self.fallback_type_rejections += 1
            elif timed_out:
                self.fallback_timeouts += 1
            elif success:
                self.fallback_successes += 1
            else:
                self.fallback_failures += 1
            self.total_fallback_duration_s += duration

    def snapshot(self) -> dict:
        with self._lock:
            fb = self.total_fallbacks
            return {
                "total_conversions": self.total_conversions,
                "total_qa": self.total_qa,
                "total_fallbacks": fb,
                "fallback_successes": self.fallback_successes,
                "fallback_failures": self.fallback_failures,
                "fallback_timeouts": self.fallback_timeouts,
                "fallback_type_rejections": self.fallback_type_rejections,
                "avg_fallback_duration_s": round(
                    self.total_fallback_duration_s / fb, 2
                ) if fb > 0 else 0.0,
            }



@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Log detailed request validation errors to aid debugging 422 issues."""
    try:
        body = await request.body()
    except Exception:
        body = b""
    logger.error("Request validation failed: %s", exc.errors())
    # Body may be bytes; limit size to avoid noisy logs
    preview = body[:2048]
    logger.debug("Raw request body preview (up to 2KB): %r", preview)
    return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content={"detail": exc.errors()})


def _is_knowledge_hub_callback(url: str) -> tuple[bool, str | None]:
    """判断回调是否为 Knowledge Hub（query token 或路径特征）。"""
    try:
        parsed = urlparse(url)
        token = parse_qs(parsed.query).get("token", [None])[0]
        is_kh_path = "callback/forma/convert" in parsed.path
        return bool(token) or is_kh_path, token
    except Exception:
        return False, None


async def _send_callback(
    client: httpx.AsyncClient,
    callback_url: str,
    callback: CallbackPayload,
) -> None:
    """统一的回调发送逻辑，兼容 Knowledge Hub 规范与旧格式."""

    is_kh, token_in_query = _is_knowledge_hub_callback(callback_url)

    headers: dict[str, str] = {}
    if not token_in_query and CALLBACK_TOKEN:
        headers["X-Callback-Token"] = CALLBACK_TOKEN

    # Knowledge Hub 载荷
    if is_kh:
        kh_payload = KnowledgeHubCallbackPayload(
            request_id=callback.request_id,
            status=callback.status,
            markdown=callback.markdown_content if callback.status == "completed" else None,
            error=callback.error_message,
            visual_facts=getattr(callback, "visual_facts", None),
        ).model_dump(by_alias=True, exclude_none=True)
        payload = kh_payload
    else:
        payload = callback.model_dump(by_alias=True, exclude_none=True)

    logger.debug(
        "Sending callback (KH=%s) to %s with keys: %s",
        is_kh or bool(headers),
        callback_url,
        list(payload.keys()),
    )

    try:
        await client.post(callback_url, json=payload, headers=headers or None)
    except httpx.HTTPError as http_exc:
        logger.error("Callback failed: %s", http_exc)
        logger.debug("Callback payload: %s", payload)


def _position_label(position_type: str, position_meta: dict[str, object]) -> str:
    if position_type == "tabular_anchor":
        sheet = str(position_meta.get("sheet", "") or "").strip()
        from_row = int(position_meta.get("from_row", 0) or 0)
        to_row = int(position_meta.get("to_row", 0) or 0)
        from_col = int(position_meta.get("from_col", 0) or 0)
        to_col = int(position_meta.get("to_col", 0) or 0)
        from_col_label = str(position_meta.get("from_col_label", "") or "").strip()
        to_col_label = str(position_meta.get("to_col_label", "") or "").strip()

        row_label = ""
        if from_row > 0:
            row_label = f"row {from_row}"
            if to_row > from_row:
                row_label = f"rows {from_row}-{to_row}"

        col_label = ""
        if from_col_label:
            col_label = f"col {from_col_label}"
            if to_col_label and to_col_label != from_col_label:
                col_label = f"cols {from_col_label}-{to_col_label}"
        elif from_col > 0:
            col_label = f"col {from_col}"
            if to_col > from_col:
                col_label = f"cols {from_col}-{to_col}"

        parts = []
        if sheet:
            parts.append(f'sheet "{sheet}"')
        if row_label:
            parts.append(row_label)
        if col_label:
            parts.append(col_label)
        return ", ".join(parts)

    return ""


async def _upload_visual_assets(
    client: httpx.AsyncClient,
    task: ConversionTask,
    visual_assets: list,
) -> list[dict[str, str]]:
    if not visual_assets or not task.asset_upload_url or not task.asset_upload_token or not task.document_id:
        return []

    uploaded: list[dict[str, str]] = []
    for asset in visual_assets:
        try:
            response = await client.post(
                str(task.asset_upload_url),
                headers={"X-Forma-Token": task.asset_upload_token},
                data={
                    "document_id": task.document_id,
                    "paragraph_index": "0",
                    "page": "0",
                    "sha256": hashlib.sha256(asset.content).hexdigest(),
                    "position_type": asset.position_type or "",
                    "position_meta": json.dumps(asset.position_meta or {}, ensure_ascii=False),
                },
                files={
                    "file": (
                        asset.filename,
                        asset.content,
                        asset.mime_type,
                    )
                },
                timeout=60.0,
            )
            response.raise_for_status()
            payload = response.json()
            data = payload.get("data", payload)
            asset_id = str(data.get("asset_id", "") or "").strip()
            preview_url = str(data.get("url", data.get("cdn_url", "")) or "").strip()
            if not asset_id or not preview_url:
                raise RuntimeError(f"asset upload response missing asset_id/url: {payload}")
            uploaded.append(
                {
                    "asset_id": asset_id,
                    "preview_url": preview_url,
                    "alt_text": asset.alt_text,
                    "caption": asset.alt_text,
                    "position_type": asset.position_type or "",
                    "position_label": _position_label(asset.position_type, asset.position_meta or {}),
                    "context_text": str((asset.position_meta or {}).get("context_text", "") or ""),
                }
            )
        except Exception as upload_exc:
            logger.warning(
                "Visual asset upload failed for request_id=%s filename=%s error=%s",
                task.request_id,
                getattr(asset, "filename", "unknown"),
                upload_exc,
            )
    return uploaded


def _append_uploaded_visual_assets(markdown: str, uploaded_assets: list[dict[str, str]]) -> str:
    if not uploaded_assets:
        return markdown

    lines = [markdown.strip()] if markdown.strip() else []
    if lines:
        lines.append("")
    lines.append("## Visual Assets")
    lines.append("")
    for item in uploaded_assets:
        heading = item["alt_text"]
        if item["position_label"] and item["position_label"] not in heading:
            heading = f'{heading} [{item["position_label"]}]'
        lines.append(f"### {heading}")
        lines.append(f'![{item["alt_text"]}]({item["preview_url"]}?asset_id={item["asset_id"]})')
        lines.append("")
    return "\n".join(lines).strip()




def _visual_facts_from_uploaded_assets(uploaded_assets: list[dict[str, object]]) -> list[dict[str, object]]:
    facts: list[dict[str, object]] = []
    for item in uploaded_assets:
        facts.append({
            "asset_id": item.get("asset_id", ""),
            "position_type": item.get("position_type", ""),
            "position_label": item.get("position_label", ""),
            "caption": item.get("caption", item.get("alt_text", "")),
            "context_text": item.get("context_text", ""),
        })
    return facts


def _on_worker_done(worker_type: str, worker_id: int, task: asyncio.Task) -> None:
    """Worker 退出时的回调：记录日志，如果是异常退出则自动重启。"""
    # 正常关闭流程中的取消，不需要重启
    if task.cancelled():
        logger.info("%s worker %s 已取消（正常关闭）。", worker_type, worker_id)
        return

    # 如果正在执行 shutdown，不要重启
    if getattr(app.state, "shutting_down", False):
        return

    exc = task.exception()
    if exc:
        logger.error(
            "CRITICAL: %s worker %s 意外崩溃: %s", worker_type, worker_id, exc)
    else:
        logger.warning(
            "%s worker %s 意外退出（无异常）。", worker_type, worker_id)

    # 自动重启
    _restart_worker(worker_type, worker_id)


def _restart_worker(worker_type: str, worker_id: int) -> None:
    """重启一个崩溃的 Worker，并更新 app.state 中的强引用。"""
    logger.info("正在重启 %s worker %s ...", worker_type, worker_id)

    if worker_type == "conversion":
        coro = conversion_worker(worker_id=worker_id)
        workers_list = getattr(app.state, "conversion_workers", [])
    elif worker_type == "qa":
        coro = qa_worker(worker_id=worker_id)
        workers_list = getattr(app.state, "qa_workers", [])
    else:
        logger.error("未知的 worker 类型: %s", worker_type)
        return

    new_task = asyncio.create_task(coro)
    new_task.add_done_callback(
        lambda t, wt=worker_type, wid=worker_id: _on_worker_done(wt, wid, t)
    )
    # 替换旧引用，保持 app.state 中的强引用
    if worker_id < len(workers_list):
        workers_list[worker_id] = new_task
    logger.info("✓ %s worker %s 已重启。", worker_type, worker_id)


@app.on_event("startup")
async def start_worker() -> None:
    logger.info("Starting workers...")
    app.state.shutting_down = False
    app.state.metrics = ConversionMetrics()
    try:
        # 启动多个 conversion worker
        logger.info("Creating %s conversion workers", CONVERSION_WORKERS)
        app.state.conversion_workers = []
        for i in range(CONVERSION_WORKERS):
            task = asyncio.create_task(conversion_worker(worker_id=i))
            task.add_done_callback(
                lambda t, wid=i: _on_worker_done("conversion", wid, t)
            )
            app.state.conversion_workers.append(task)
        logger.info("✓ Started %s conversion workers.", CONVERSION_WORKERS)

        # 启动多个 QA worker
        logger.info("Creating %s QA workers", QA_WORKERS)
        app.state.qa_workers = []
        for i in range(QA_WORKERS):
            task = asyncio.create_task(qa_worker(worker_id=i))
            task.add_done_callback(
                lambda t, wid=i: _on_worker_done("qa", wid, t)
            )
            app.state.qa_workers.append(task)
        logger.info("✓ Started %s QA workers.", QA_WORKERS)
        logger.info("=" * 60)
        logger.info("Forma API Server is ready to accept requests.")
        logger.info("=" * 60)
    except Exception:
        logger.exception("Error starting workers")


@app.on_event("shutdown")
async def stop_worker() -> None:
    """优雅关闭所有 Worker：发送取消信号 → 等待退出 → 清理引用。"""
    logger.info("Shutting down workers...")
    # 设置标志位，防止 _on_worker_done 回调在关闭期间误重启 Worker
    app.state.shutting_down = True

    all_workers: list[asyncio.Task] = []
    if hasattr(app.state, "conversion_workers"):
        all_workers.extend(app.state.conversion_workers)
    if hasattr(app.state, "qa_workers"):
        all_workers.extend(app.state.qa_workers)

    if not all_workers:
        logger.warning("No workers found to shut down.")
        return

    # 1. 发送取消信号
    for worker in all_workers:
        worker.cancel()

    # 2. 并行等待所有 worker 处理完取消逻辑（如 finally 块）
    results = await asyncio.gather(*all_workers, return_exceptions=True)
    for i, result in enumerate(results):
        if isinstance(result, asyncio.CancelledError):
            continue
        if isinstance(result, Exception):
            logger.warning(
                "Worker %s exited with error during shutdown: %s", i, result)

    logger.info("All %s workers have been shut down.", len(all_workers))

    # 关闭 IPC 线程池
    _ipc_thread_pool.shutdown(wait=False)


@app.post("/api/v1/convert", response_model=ConvertResponse, status_code=status.HTTP_202_ACCEPTED)
async def convert(request: ConvertRequest) -> ConvertResponse:
    """Enqueue a conversion task and return immediately."""

    task_id = str(uuid.uuid4())
    task = ConversionTask(task_id=task_id, **request.model_dump())
    try:
        await asyncio.wait_for(conversion_queue.put(task), timeout=QUEUE_PUT_TIMEOUT)
    except asyncio.TimeoutError:
        from fastapi import HTTPException

        logger.error("Conversion queue is full, request rejected: %s", task_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Server busy: conversion queue is full. Please retry later.",
        )
    return ConvertResponse(task_id=task_id)


@app.post("/api/v1/convert-by-content", response_model=ConvertResponse, status_code=status.HTTP_202_ACCEPTED)
async def convert_by_content(request: ConvertByContentRequest) -> ConvertResponse:
    """Enqueue inline markdown content for normalization and callback."""

    content_bytes = len(request.markdown_content.encode("utf-8"))
    if content_bytes > MAX_INLINE_MD_BYTES:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Markdown content exceeds allowed size ({MAX_INLINE_MD_BYTES} bytes)",
        )

    task_id = str(uuid.uuid4())
    task = ConversionTask(
        task_id=task_id,
        request_id=request.request_id,
        document_id=request.document_id,
        callback_url=request.callback_url,
        inline_markdown=request.markdown_content,
        source_url=None,
        asset_upload_url=request.asset_upload_url,
        asset_upload_token=request.asset_upload_token,
    )
    try:
        await asyncio.wait_for(conversion_queue.put(task), timeout=QUEUE_PUT_TIMEOUT)
    except asyncio.TimeoutError:
        from fastapi import HTTPException

        logger.error("Conversion queue is full, request rejected: %s", task_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Server busy: conversion queue is full. Please retry later.",
        )
    return ConvertResponse(task_id=task_id)


@app.post("/api/v1/generate-qa", response_model=GenerateQAResponse, status_code=status.HTTP_202_ACCEPTED)
async def generate_qa(request: GenerateQARequest) -> GenerateQAResponse:
    """Enqueue a FAQ generation task and return immediately."""

    task_id = str(uuid.uuid4())
    task = GenerateQATask(task_id=task_id, **request.model_dump())
    try:
        await asyncio.wait_for(qa_queue.put(task), timeout=QUEUE_PUT_TIMEOUT)
    except asyncio.TimeoutError:
        from fastapi import HTTPException

        logger.error("QA queue is full, request rejected: %s", task_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Server busy: QA queue is full. Please retry later.",
        )
    return GenerateQAResponse(task_id=task_id)


# 异步工作进程，不停的从队列中获取任务并处理
async def conversion_worker(worker_id: int) -> None:
    """后台 Worker：循环从队列中取出文档转换任务并处理。"""

    async with httpx.AsyncClient(timeout=None) as client:
        while True:
            try:
                task = await conversion_queue.get()
                logger.debug(
                    "Conversion worker %s picked up task: %s", worker_id, task.task_id)
                try:
                    await process_conversion_task(task, client)
                except Exception:
                    logger.exception(
                        "Conversion worker %s: 处理任务时发生未捕获异常", worker_id)
                finally:
                    conversion_queue.task_done()
            except asyncio.CancelledError:
                logger.info("Conversion worker %s 收到取消信号，正在退出。", worker_id)
                raise
            except Exception:
                logger.exception(
                    "CRITICAL: Conversion worker %s 循环异常，1 秒后重试...", worker_id)
                await asyncio.sleep(1)


async def qa_worker(worker_id: int) -> None:
    """后台 Worker：循环从队列中取出 QA 生成任务并处理。"""

    async with httpx.AsyncClient(timeout=None) as client:
        while True:
            try:
                task = await qa_queue.get()
                logger.debug(
                    "QA worker %s picked up task: %s", worker_id, task.task_id)
                try:
                    await process_qa_task(task, client)
                except Exception:
                    logger.exception(
                        "QA worker %s: 处理任务时发生未捕获异常", worker_id)
                finally:
                    qa_queue.task_done()
            except asyncio.CancelledError:
                logger.info("QA worker %s 收到取消信号，正在退出。", worker_id)
                raise
            except Exception:
                logger.exception(
                    "CRITICAL: QA worker %s 循环异常，1 秒后重试...", worker_id)
                await asyncio.sleep(1)


async def process_qa_task(task: GenerateQATask, client: httpx.AsyncClient) -> None:
    """Process FAQ generation task and callback the result."""
    app.state.metrics.record_qa()


    callback = QACallbackPayload(request_id=task.request_id, status="failed")
    try:
        logger.debug(
            "QA Task received: %s (request_id=%s)", task.task_id, task.request_id
        )

        with tempfile.TemporaryDirectory() as temp_dir_str:
            temp_dir = Path(temp_dir_str)

            input_path = temp_dir / "input.md"
            input_path.write_text(task.markdown_content, encoding="utf-8")
            logger.debug("Markdown content saved to temporary file: %s", input_path)

            output_dir = temp_dir / "output"
            output_dir.mkdir()

            try:
                logger.debug("About to start FAQ generation process")

                from forma.qa.pipeline_v2 import run_knowledge_pipeline

                try:
                    qa_func = partial(
                        run_knowledge_pipeline,
                        input_path=input_path,
                        output_dir=output_dir,
                        export_csv=False,
                    )
                    await run_in_subprocess(qa_func, timeout=QA_TIMEOUT)
                    logger.debug("FAQ generation completed successfully")
                except asyncio.TimeoutError as exc:
                    logger.warning(
                        "FAQ generation timed out after %s seconds", QA_TIMEOUT
                    )
                    raise RuntimeError(
                        f"FAQ generation timed out after {QA_TIMEOUT} seconds"
                    ) from exc
            except Exception as gen_exc:
                logger.error("FAQ generation error: %s", gen_exc)
                raise RuntimeError(
                    f"FAQ generation error: {gen_exc}"
                ) from gen_exc

            logger.debug("Checking for output files in %s", output_dir)
            output_files = list(output_dir.glob("*_knowledge_base.jsonl"))
            if not output_files:
                logger.error("No output files found for FAQ generation")
                raise RuntimeError("FAQ generation produced no output")

            logger.debug(
                "Found %s output files. Reading first file: %s",
                len(output_files),
                output_files[0],
            )

            qa_pairs = []
            with output_files[0].open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        qa_pairs.append(json.loads(line))

            callback.status = "completed"
            qa_object = {"qa_pairs": qa_pairs}
            callback.faq_json = json.dumps(qa_object, ensure_ascii=False)
            logger.debug(
                "Successfully generated FAQ content, with %s QA pairs",
                len(qa_pairs),
            )

            try:
                DATA_DIR.mkdir(exist_ok=True)

                timestamp = time.strftime("%Y%m%d_%H%M%S")
                data_content = f"Request ID: {task.request_id}\n"
                data_content += f"Timestamp: {timestamp}\n"
                data_content += f"QA Pairs Count: {len(qa_pairs)}\n\n"
                data_content += "FAQ JSON:\n"
                data_content += callback.faq_json

                timestamped_file = DATA_DIR / (
                    f"faq_data_{timestamp}_{task.request_id}.txt"
                )
                with timestamped_file.open("w", encoding="utf-8") as f:
                    f.write(data_content)
                logger.debug(
                    "FAQ data saved to timestamped file: %s", timestamped_file
                )

                fixed_file = DATA_DIR / "data.txt"
                with fixed_file.open("w", encoding="utf-8") as f:
                    f.write(data_content)
                logger.debug("FAQ data also saved to fixed file: %s", fixed_file)
            except Exception as save_exc:
                logger.warning("Failed to save FAQ data to file: %s", save_exc)
    except Exception as exc:
        import traceback

        tb_str = traceback.format_exc(limit=5)
        callback.error_message = (
            f"FAQ Generation Error - {exc.__class__.__name__}: {exc}\n{tb_str}"
        )
        logger.error(
            "QA task processing failed: %s: %s", exc.__class__.__name__, exc
        )
    finally:
        await _send_callback(client, str(task.callback_url), callback)


async def process_conversion_task(task: ConversionTask, client: httpx.AsyncClient) -> None:
    """下载、转换并处理回调。使用进程隔离执行，超时可 kill 回收。"""
    app.state.metrics.record_conversion()

    start_time = time.time()
    callback = CallbackPayload(request_id=task.request_id, status="failed")
    input_path: Path | None = None
    conversion_results = []
    try:
        if task.inline_markdown is not None:
            logger.debug(
                "Task received: %s (request_id=%s, inline_markdown=True, size=%s bytes)",
                task.task_id,
                task.request_id,
                len(task.inline_markdown.encode("utf-8")),
            )
            from .shared.utils.markdown_cleaner import MarkdownCleaner

            callback.status = "completed"
            callback.markdown_content = MarkdownCleaner.normalize_inline_markdown(task.inline_markdown)
            elapsed_ms = (time.time() - start_time) * 1000
            if elapsed_ms < MIN_CALLBACK_DELAY_MS:
                await asyncio.sleep((MIN_CALLBACK_DELAY_MS - elapsed_ms) / 1000)
            return

        if task.source_url is None:
            raise RuntimeError("source_url is required for file conversion tasks")

        logger.debug(
            "Task received: %s (request_id=%s, source_url=%s)",
            task.task_id,
            task.request_id,
            task.source_url,
        )

        with tempfile.TemporaryDirectory() as temp_dir_str:
            temp_dir = Path(temp_dir_str)

            # 解析文件名，从task.source_url里提取文件名，得到 decoded_filename
            url_path = Path(str(task.source_url))
            original_filename = url_path.name

            from urllib.parse import unquote

            decoded_filename = unquote(original_filename)
            logger.debug("Original filename: %s", decoded_filename)

            input_path = temp_dir / decoded_filename

            try:
                url = str(task.source_url)
                logger.debug("Attempting to download file from URL: %s", url)

                resp = await client.get(url)
                resp.raise_for_status()
                input_path.write_bytes(resp.content)
                logger.debug(
                    "File download successful. Size: %s bytes, saved to: %s",
                    len(resp.content),
                    input_path,
                )
                logger.debug("File extension: %s", input_path.suffix)

            except Exception as download_exc:
                logger.exception("File download failed: %s", download_exc)
                raise RuntimeError(
                    f"Failed to download file: {download_exc}"
                ) from download_exc

            output_dir = temp_dir / "output"
            output_dir.mkdir()

            try:
                logger.debug(
                    "About to start conversion process for file: %s", input_path
                )

                try:
                    conversion_func = partial(
                        run_conversion,
                        inputs=[input_path],
                        output_dir=output_dir,
                        strategy=Strategy.AUTO,
                        recursive=False,
                        use_ocr_for_images=False,
                    )
                    conversion_results = await run_in_subprocess(conversion_func, timeout=CONVERSION_TIMEOUT)
                    logger.debug("Conversion completed successfully")

                # 主流程超时 → 尝试 fallback（进程隔离 + 独立超时）
                except asyncio.TimeoutError:
                    logger.warning(
                        "Conversion timed out after %s seconds for %s",
                        CONVERSION_TIMEOUT,
                        input_path.name,
                    )
                    fallback_start = time.time()
                    suffix = input_path.suffix.lower()

                    # 修复项1：文件类型检查 - VlmParser 仅支持 PDF 和图片
                    if suffix not in VLM_SUPPORTED_SUFFIXES:
                        fb_dur = time.time() - fallback_start
                        app.state.metrics.record_fallback(
                            success=False, duration=fb_dur, type_rejected=True
                        )
                        raise RuntimeError(
                            f"转换超时，且文件类型 '{suffix}' 不支持 fallback 处理"
                        )

                    try:
                        logger.info(
                            "Using fallback processing for %s (timeout=%ss)",
                            input_path.name, FALLBACK_TIMEOUT,
                        )
                        fallback_func = partial(
                            run_fallback,
                            path=input_path,
                            prompt_name="default_image_description",
                        )
                        # 修复项2+3+4：进程隔离 + 超时控制 + kill 连带回收
                        final_md, text_char_count, low_confidence = (
                            await run_in_subprocess(fallback_func, timeout=FALLBACK_TIMEOUT)
                        )

                        # 修复项5：fallback 结果也过 confidence 检查
                        from .shared.config import get_vlm_config
                        threshold = get_vlm_config().auto_threshold
                        if low_confidence or text_char_count < threshold:
                            logger.warning(
                                "Fallback 结果置信度低 (chars=%s, threshold=%s)",
                                text_char_count, threshold,
                            )

                        from .shared.utils.markdown_cleaner import MarkdownCleaner
                        cleaned_md = MarkdownCleaner.clean_markdown(final_md)
                        output_file = output_dir / f"{input_path.stem}.md"
                        output_file.write_text(cleaned_md, encoding="utf-8")

                        fb_dur = time.time() - fallback_start
                        app.state.metrics.record_fallback(success=True, duration=fb_dur)
                        logger.info(
                            "Fallback 成功: file=%s, 耗时=%.2fs, chars=%s",
                            input_path.name, fb_dur, text_char_count,
                        )

                    except asyncio.TimeoutError:
                        fb_dur = time.time() - fallback_start
                        app.state.metrics.record_fallback(
                            success=False, duration=fb_dur, timed_out=True
                        )
                        raise RuntimeError(
                            f"Fallback 也超时 ({FALLBACK_TIMEOUT}s)，放弃处理 {input_path.name}"
                        )
                    except Exception as fb_exc:
                        if not isinstance(fb_exc, RuntimeError) or "超时" not in str(fb_exc):
                            fb_dur = time.time() - fallback_start
                            app.state.metrics.record_fallback(success=False, duration=fb_dur)
                        raise

            except Exception as conv_exc:
                logger.exception("Conversion engine error: %s", conv_exc)
                raise RuntimeError(
                    f"Conversion engine error: {conv_exc}"
                ) from conv_exc

            logger.debug("Checking for output files in %s", output_dir)
            output_files = list(output_dir.glob("*.md"))
            if not output_files:
                file_name = Path(str(task.source_url)).name
                logger.error("No output files found for %s", file_name)
                raise RuntimeError(
                    f"Conversion produced no output for file: {file_name}"
                )

            logger.debug(
                "Found %s output files. Reading first file: %s",
                len(output_files),
                output_files[0],
            )
            markdown = output_files[0].read_text(encoding="utf-8")
            visual_assets = []
            for result in conversion_results or []:
                visual_assets.extend(getattr(result, "visual_assets", []) or [])
            uploaded_assets = await _upload_visual_assets(client, task, visual_assets)
            if uploaded_assets:
                markdown = _append_uploaded_visual_assets(markdown, uploaded_assets)
                callback.visual_facts = _visual_facts_from_uploaded_assets(uploaded_assets)
            callback.status = "completed"
            callback.markdown_content = markdown
            logger.debug(
                "Successfully read markdown content, length: %s characters",
                len(markdown),
            )
    except Exception as exc:
        import traceback

        tb_str = traceback.format_exc(limit=5)
        if task.source_url is not None:
            file_info = f"File: {Path(str(task.source_url)).name}"
        else:
            file_info = "Inline markdown"
        callback.error_message = (
            f"{file_info} - {exc.__class__.__name__}: {exc}\n{tb_str}"
        )
        logger.error(
            "Task processing failed: %s: %s", exc.__class__.__name__, exc
        )
    finally:
        await _send_callback(client, str(task.callback_url), callback)


@app.get("/metrics")
async def metrics():
    """返回可观测性指标快照。"""
    return app.state.metrics.snapshot()
