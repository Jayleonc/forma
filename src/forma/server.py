"""Async callback-driven FastAPI server for forma."""

from __future__ import annotations

import asyncio
import tempfile
import uuid
from pathlib import Path

import httpx
from fastapi import FastAPI, status, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, AnyHttpUrl, Field, ConfigDict
import contextlib

from .conversion.workflow import run_conversion
from .shared.custom_types import Strategy
from .shared.utils.markdown_cleaner import MarkdownCleaner



class ConvertRequest(BaseModel):
    # Canonicalize to job_id as external and internal name
    model_config = ConfigDict(populate_by_name=True)

    job_id: str
    source_url: AnyHttpUrl
    callback_url: AnyHttpUrl


class ConvertResponse(BaseModel):
    task_id: str
    status: str = "processing"


class CallbackPayload(BaseModel):
    # Output uses camelCase key `jobId` for the callback payload
    model_config = ConfigDict(populate_by_name=True)

    job_id: str 
    status: str
    markdown_content: str | None = None
    error_message: str | None = None


class ConversionTask(BaseModel):
    task_id: str
    job_id: str
    source_url: AnyHttpUrl
    callback_url: AnyHttpUrl


app = FastAPI()
queue: asyncio.Queue[ConversionTask] = asyncio.Queue()


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Log detailed request validation errors to aid debugging 422 issues."""
    try:
        body = await request.body()
    except Exception:
        body = b""
    print("[ERROR] Request validation failed:", exc.errors())
    # Body may be bytes; limit size to avoid noisy logs
    preview = body[:2048]
    print(f"[DEBUG] Raw request body preview (up to 2KB): {preview!r}")
    return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content={"detail": exc.errors()})


@app.on_event("startup")
async def start_worker() -> None:
    app.state.worker = asyncio.create_task(worker())


@app.on_event("shutdown")
async def stop_worker() -> None:
    app.state.worker.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await app.state.worker


@app.post("/api/v1/convert", response_model=ConvertResponse, status_code=status.HTTP_202_ACCEPTED)
async def convert(request: ConvertRequest) -> ConvertResponse:
    """Enqueue a conversion task and return immediately."""

    task_id = str(uuid.uuid4())
    task = ConversionTask(task_id=task_id, **request.model_dump())
    await queue.put(task)
    return ConvertResponse(task_id=task_id)


async def worker() -> None:
    """Background worker that processes conversion tasks."""

    async with httpx.AsyncClient(timeout=None) as client:
        while True:
            task = await queue.get()
            try:
                await process_task(task, client)
            finally:
                queue.task_done()


async def process_task(task: ConversionTask, client: httpx.AsyncClient) -> None:
    """Download, convert and callback the result."""

    callback = CallbackPayload(job_id=task.job_id, status="failed")
    input_path = None
    try:
        # Log task received
        print(f"[DEBUG] Task received: {task.task_id}, job_id: {task.job_id}, source_url: {task.source_url}")
        
        with tempfile.TemporaryDirectory() as temp_dir_str:
            temp_dir = Path(temp_dir_str)
            
            # 从URL中提取文件名和后缀
            url_path = Path(str(task.source_url))
            original_filename = url_path.name
            
            # 解码URL编码的文件名
            from urllib.parse import unquote
            decoded_filename = unquote(original_filename)
            print(f"[DEBUG] Original filename: {decoded_filename}")
            
            # 保留原始文件后缀
            input_path = temp_dir / decoded_filename
            
            # Download file
            try:
                url = str(task.source_url)
                print(f"[DEBUG] Attempting to download file from URL: {url}")
                
                resp = await client.get(url)
                resp.raise_for_status()
                input_path.write_bytes(resp.content)
                print(f"[DEBUG] File download successful. Size: {len(resp.content)} bytes, saved to: {input_path}")
                print(f"[DEBUG] File extension: {input_path.suffix}")

            except Exception as download_exc:
                print(f"[ERROR] File download failed: {download_exc}")
                raise RuntimeError(f"Failed to download file: {download_exc}") from download_exc

            output_dir = temp_dir / "output"
            output_dir.mkdir()

            # Run conversion
            try:
                print(f"[DEBUG] About to start conversion process for file: {input_path}")
                run_conversion(
                    inputs=[input_path],
                    output_dir=output_dir,
                    strategy=Strategy.AUTO,
                    recursive=False,
                    use_ocr_for_images=False,  # 默认使用VLM处理图片，而不是OCR
                )
                print(f"[DEBUG] Conversion completed successfully")
            except Exception as conv_exc:
                print(f"[ERROR] Conversion engine error: {conv_exc}")
                raise RuntimeError(f"Conversion engine error: {conv_exc}") from conv_exc

            # Check output
            print(f"[DEBUG] Checking for output files in {output_dir}")
            output_files = list(output_dir.glob("*.md"))
            if not output_files:
                # 直接抛出异常，不创建 fallback 文件
                file_name = Path(str(task.source_url)).name
                print(f"[ERROR] No output files found for {file_name}")
                raise RuntimeError(f"Conversion produced no output for file: {file_name}")
            
            print(f"[DEBUG] Found {len(output_files)} output files. Reading first file: {output_files[0]}")
            markdown = output_files[0].read_text(encoding="utf-8")
            # 注意: 这里不需要再次清洗Markdown内容
            # 因为workflow.py中已经在所有输出路径应用了MarkdownCleaner.clean_markdown()
            callback.status = "completed"
            callback.markdown_content = markdown
            print(f"[DEBUG] Successfully read markdown content, length: {len(markdown)} characters")
    except Exception as exc:
        # Capture detailed error information
        import traceback
        tb_str = traceback.format_exc(limit=5)
        file_info = f"File: {Path(str(task.source_url)).name}" if input_path else "Unknown file"
        callback.error_message = f"{file_info} - {exc.__class__.__name__}: {exc}\n{tb_str}"
        print(f"[ERROR] Task processing failed: {exc.__class__.__name__}: {exc}")
    finally:
        try:
            callback_url = str(task.callback_url)
            print(f"[DEBUG] Sending callback to {callback_url}, status: {callback.status}")

            # Send jobId (camelCase) as required by the Go callback API
            payload = callback.model_dump(by_alias=True)
            await client.post(callback_url, json=payload)
            print(f"[DEBUG] Callback sent successfully with keys: {list(payload.keys())}")
        except httpx.HTTPError as http_exc:
            # Log callback failure without affecting main flow
            print(f"[ERROR] Callback failed: {http_exc}")
            print(f"[DEBUG] Callback payload: {callback.model_dump()}")



