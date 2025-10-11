"""Async callback-driven FastAPI server for forma."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, status, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, AnyHttpUrl, Field, ConfigDict
import contextlib

from .conversion.workflow import run_conversion
from .shared.custom_types import Strategy


class ConvertRequest(BaseModel):
    # Canonicalize to request_id as external and internal name
    model_config = ConfigDict(populate_by_name=True)

    request_id: str
    source_url: AnyHttpUrl
    callback_url: AnyHttpUrl


class ConvertResponse(BaseModel):
    task_id: str
    status: str = "processing"


class CallbackPayload(BaseModel):
    # 使用下划线风格的字段名
    model_config = ConfigDict(populate_by_name=True)

    request_id: str
    status: str
    markdown_content: str | None = None
    error_message: str | None = None


class ConversionTask(BaseModel):
    task_id: str
    request_id: str
    source_url: AnyHttpUrl
    callback_url: AnyHttpUrl


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


app = FastAPI()
conversion_queue: asyncio.Queue[ConversionTask] = asyncio.Queue()
qa_queue: asyncio.Queue[GenerateQATask] = asyncio.Queue()  # 新增 FAQ 生成任务队列


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
    print("[DEBUG] Starting workers...")
    try:
        # 启动多个 conversion worker
        num_conversion_workers = int(os.environ.get("CONVERSION_WORKERS", 4))
        print(f"[DEBUG] Creating {num_conversion_workers} conversion workers")
        app.state.conversion_workers = [
            asyncio.create_task(conversion_worker(worker_id=i))
            for i in range(num_conversion_workers)
        ]
        print(f"[INFO] Started {num_conversion_workers} conversion workers.")

        # 启动多个 QA worker
        num_qa_workers = int(os.environ.get("QA_WORKERS", 2))
        print(f"[DEBUG] Creating {num_qa_workers} QA workers")
        app.state.qa_workers = [
            asyncio.create_task(qa_worker(worker_id=i))
            for i in range(num_qa_workers)
        ]
        print(f"[INFO] Started {num_qa_workers} QA workers.")
    except Exception as e:
        print(f"[ERROR] Error starting workers: {e.__class__.__name__}: {e}")
        import traceback
        print(traceback.format_exc())


@app.on_event("shutdown")
async def stop_worker() -> None:
    print("[DEBUG] Shutting down workers...")
    try:
        # 取消所有 worker 任务
        print("[DEBUG] Cancelling conversion workers...")
        if hasattr(app.state, 'conversion_workers'):
            for worker in app.state.conversion_workers:
                worker.cancel()
        else:
            print("[WARNING] No conversion_workers found in app.state")
        
        print("[DEBUG] Cancelling QA workers...")
        if hasattr(app.state, 'qa_workers'):
            for worker in app.state.qa_workers:
                worker.cancel()
        else:
            print("[WARNING] No qa_workers found in app.state")

        # 等待所有 worker 任务完成取消
        print("[DEBUG] Waiting for conversion workers to complete cancellation...")
        if hasattr(app.state, 'conversion_workers'):
            for worker in app.state.conversion_workers:
                with contextlib.suppress(asyncio.CancelledError):
                    await worker
        
        print("[DEBUG] Waiting for QA workers to complete cancellation...")
        if hasattr(app.state, 'qa_workers'):
            for worker in app.state.qa_workers:
                with contextlib.suppress(asyncio.CancelledError):
                    await worker
        
        print("[INFO] All workers have been shut down.")
    except Exception as e:
        print(f"[ERROR] Error shutting down workers: {e.__class__.__name__}: {e}")
        import traceback
        print(traceback.format_exc())


@app.post("/api/v1/convert", response_model=ConvertResponse, status_code=status.HTTP_202_ACCEPTED)
async def convert(request: ConvertRequest) -> ConvertResponse:
    """Enqueue a conversion task and return immediately."""

    task_id = str(uuid.uuid4())
    task = ConversionTask(task_id=task_id, **request.model_dump())
    await conversion_queue.put(task)
    return ConvertResponse(task_id=task_id)


@app.post("/api/v1/generate-qa", response_model=GenerateQAResponse, status_code=status.HTTP_202_ACCEPTED)
async def generate_qa(request: GenerateQARequest) -> GenerateQAResponse:
    """Enqueue a FAQ generation task and return immediately."""

    task_id = str(uuid.uuid4())
    task = GenerateQATask(task_id=task_id, **request.model_dump())
    await qa_queue.put(task)
    return GenerateQAResponse(task_id=task_id)


async def conversion_worker(worker_id: int) -> None:
    """Background worker that processes document conversion tasks."""

    async with httpx.AsyncClient(timeout=None) as client:
        while True:
            task = await conversion_queue.get()
            print(
                f"[DEBUG] Conversion worker {worker_id} picked up task: {task.task_id}")
            try:
                await process_conversion_task(task, client)
            finally:
                conversion_queue.task_done()


async def qa_worker(worker_id: int) -> None:
    """Background worker that processes FAQ generation tasks."""

    async with httpx.AsyncClient(timeout=None) as client:
        while True:
            task = await qa_queue.get()
            print(f"[DEBUG] QA worker {worker_id} picked up task: {task.task_id}")
            try:
                await process_qa_task(task, client)
            finally:
                qa_queue.task_done()


async def process_qa_task(task: GenerateQATask, client: httpx.AsyncClient) -> None:
    """Process FAQ generation task and callback the result."""

    callback = QACallbackPayload(request_id=task.request_id, status="failed")
    try:
        # Log task received
        print(
            f"[DEBUG] QA Task received: {task.task_id}, request_id: {task.request_id}")

        with tempfile.TemporaryDirectory() as temp_dir_str:
            temp_dir = Path(temp_dir_str)

            # 创建临时文件存储 Markdown 内容
            input_path = temp_dir / "input.md"
            input_path.write_text(task.markdown_content, encoding="utf-8")
            print(
                f"[DEBUG] Markdown content saved to temporary file: {input_path}")

            output_dir = temp_dir / "output"
            output_dir.mkdir()

            # 运行 FAQ 生成
            try:
                print(f"[DEBUG] About to start FAQ generation process")

                # 导入 qa-v2 的 run_knowledge_pipeline 函数
                from forma.qa.pipeline_v2 import run_knowledge_pipeline

                # 运行知识库生成流水线 - 使用 asyncio.to_thread 避免阻塞事件循环
                # 并使用 asyncio.wait_for 实现超时控制
                timeout_seconds = 600.0  # 10分钟超时
                try:
                    await asyncio.wait_for(
                        asyncio.to_thread(
                            run_knowledge_pipeline,
                            input_path=input_path,
                            output_dir=output_dir,
                            export_csv=False,
                        ),
                        timeout=timeout_seconds
                    )
                    print(f"[DEBUG] FAQ generation completed successfully")
                except asyncio.TimeoutError:
                    print(
                        f"[WARNING] FAQ generation timed out after {timeout_seconds} seconds")
                    raise RuntimeError(
                        f"FAQ generation timed out after {timeout_seconds} seconds")
            except Exception as gen_exc:
                print(f"[ERROR] FAQ generation error: {gen_exc}")
                raise RuntimeError(
                    f"FAQ generation error: {gen_exc}") from gen_exc

            # 检查输出
            print(f"[DEBUG] Checking for output files in {output_dir}")
            output_files = list(output_dir.glob("*_knowledge_base.jsonl"))
            if not output_files:
                print(f"[ERROR] No output files found for FAQ generation")
                raise RuntimeError(f"FAQ generation produced no output")

            print(
                f"[DEBUG] Found {len(output_files)} output files. Reading first file: {output_files[0]}")

            # 读取生成的 JSONL 文件
            qa_pairs = []
            with output_files[0].open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        qa_pairs.append(json.loads(line))

            # 将 QA 对列表封装为对象，避免顶层数组
            callback.status = "completed"

            # 创建一个对象，将 QA 对列表放在 qa_pairs 字段中
            qa_object = {
                "qa_pairs": qa_pairs
            }

            # 将对象转换为 JSON 字符串
            callback.faq_json = json.dumps(qa_object, ensure_ascii=False)
            print(
                f"[DEBUG] Successfully generated FAQ content, with {len(qa_pairs)} QA pairs")

            # 将生成的 FAQ 数据保存到文件
            try:
                # 确保数据目录存在
                data_dir = Path("./data")
                data_dir.mkdir(exist_ok=True)

                # 准备要写入的数据内容
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                data_content = f"Request ID: {task.request_id}\n"
                data_content += f"Timestamp: {timestamp}\n"
                data_content += f"QA Pairs Count: {len(qa_pairs)}\n\n"
                data_content += "FAQ JSON:\n"
                data_content += callback.faq_json

                # 1. 保存到带时间戳的文件
                timestamped_file = data_dir / \
                    f"faq_data_{timestamp}_{task.request_id}.txt"
                with timestamped_file.open("w", encoding="utf-8") as f:
                    f.write(data_content)
                print(
                    f"[DEBUG] FAQ data saved to timestamped file: {timestamped_file}")

                # 2. 同时保存到固定名称的文件 data.txt
                fixed_file = data_dir / "data.txt"
                with fixed_file.open("w", encoding="utf-8") as f:
                    f.write(data_content)
                print(
                    f"[DEBUG] FAQ data also saved to fixed file: {fixed_file}")
            except Exception as save_exc:
                print(f"[WARNING] Failed to save FAQ data to file: {save_exc}")
    except Exception as exc:
        # 捕获详细的错误信息
        import traceback
        tb_str = traceback.format_exc(limit=5)
        callback.error_message = f"FAQ Generation Error - {exc.__class__.__name__}: {exc}\n{tb_str}"
        print(
            f"[ERROR] QA task processing failed: {exc.__class__.__name__}: {exc}")
    finally:
        try:
            callback_url = str(task.callback_url)
            print(
                f"[DEBUG] Sending callback to {callback_url}, status: {callback.status}")

            # 发送回调
            payload = callback.model_dump(by_alias=True)
            await client.post(callback_url, json=payload)
            print(
                f"[DEBUG] Callback sent successfully with keys: {list(payload.keys())}")
        except httpx.HTTPError as http_exc:
            # 记录回调失败，但不影响主流程
            print(f"[ERROR] Callback failed: {http_exc}")
            print(f"[DEBUG] Callback payload: {callback.model_dump()}")


async def process_conversion_task(task: ConversionTask, client: httpx.AsyncClient) -> None:
    """Download, convert and callback the result."""

    callback = CallbackPayload(request_id=task.request_id, status="failed")
    input_path = None
    try:
        # Log task received
        print(
            f"[DEBUG] Task received: {task.task_id}, request_id: {task.request_id}, source_url: {task.source_url}")

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
                print(
                    f"[DEBUG] File download successful. Size: {len(resp.content)} bytes, saved to: {input_path}")
                print(f"[DEBUG] File extension: {input_path.suffix}")

            except Exception as download_exc:
                print(f"[ERROR] File download failed: {download_exc}")
                raise RuntimeError(
                    f"Failed to download file: {download_exc}") from download_exc

            output_dir = temp_dir / "output"
            output_dir.mkdir()

            # Run conversion with timeout control
            try:
                print(
                    f"[DEBUG] About to start conversion process for file: {input_path}")

                # 使用 asyncio.wait_for 实现超时控制
                timeout_seconds = 600.0  # 10分钟超时
                try:
                    await asyncio.wait_for(
                        asyncio.to_thread(
                            run_conversion,
                            inputs=[input_path],
                            output_dir=output_dir,
                            strategy=Strategy.AUTO,
                            recursive=False,
                            use_ocr_for_images=False,  # 默认使用VLM处理图片，而不是OCR
                        ),
                        timeout=timeout_seconds
                    )
                    print(f"[DEBUG] Conversion completed successfully")

                except asyncio.TimeoutError:
                    print(
                        f"[WARNING] Conversion timed out after {timeout_seconds} seconds for {input_path.name}")
                    print(f"[DEBUG] Attempting fallback processing method")

                    # 导入备用处理函数
                    from .conversion.workflow import process_fallback

                    # 选择处理器
                    from .conversion.workflow import _select_processor
                    from .vision import OpenAIVLMClient, VlmParser

                    # 创建 VLM 客户端和解析器
                    vlm_client = OpenAIVLMClient()
                    vlm_parser = VlmParser(vlm_client)

                    # 选择处理器
                    processor = _select_processor(input_path, vlm_client)
                    if processor is None:
                        raise RuntimeError(
                            f"No suitable processor found for {input_path}")

                    # 使用备用处理方法
                    print(
                        f"[DEBUG] Using fallback processing for {input_path}")
                    final_md, _ = await asyncio.to_thread(
                        process_fallback,
                        processor=processor,
                        path=input_path,
                        vlm_client=vlm_client,
                        vlm_parser=vlm_parser,
                        prompt_name="default_image_description"
                    )

                    # 应用 Markdown 清洗
                    from .shared.utils.markdown_cleaner import MarkdownCleaner
                    cleaned_md = MarkdownCleaner.clean_markdown(final_md)

                    # 写入输出文件
                    output_file = output_dir / f"{input_path.stem}.md"
                    output_file.write_text(cleaned_md, encoding="utf-8")
                    print(
                        f"[DEBUG] Fallback processing completed and saved to {output_file}")

            except Exception as conv_exc:
                print(f"[ERROR] Conversion engine error: {conv_exc}")
                raise RuntimeError(
                    f"Conversion engine error: {conv_exc}") from conv_exc

            # Check output
            print(f"[DEBUG] Checking for output files in {output_dir}")
            output_files = list(output_dir.glob("*.md"))
            if not output_files:
                # 直接抛出异常，不创建 fallback 文件
                file_name = Path(str(task.source_url)).name
                print(f"[ERROR] No output files found for {file_name}")
                raise RuntimeError(
                    f"Conversion produced no output for file: {file_name}")

            print(
                f"[DEBUG] Found {len(output_files)} output files. Reading first file: {output_files[0]}")
            markdown = output_files[0].read_text(encoding="utf-8")
            # 注意: 这里不需要再次清洗Markdown内容
            # 因为workflow.py中已经在所有输出路径应用了MarkdownCleaner.clean_markdown()
            callback.status = "completed"
            callback.markdown_content = markdown
            print(
                f"[DEBUG] Successfully read markdown content, length: {len(markdown)} characters")
    except Exception as exc:
        # Capture detailed error information
        import traceback
        tb_str = traceback.format_exc(limit=5)
        file_info = f"File: {Path(str(task.source_url)).name}" if input_path else "Unknown file"
        callback.error_message = f"{file_info} - {exc.__class__.__name__}: {exc}\n{tb_str}"
        print(
            f"[ERROR] Task processing failed: {exc.__class__.__name__}: {exc}")
    finally:
        try:
            callback_url = str(task.callback_url)
            print(
                f"[DEBUG] Sending callback to {callback_url}, status: {callback.status}")

            # Send requestId (camelCase) as required by the Go callback API
            payload = callback.model_dump(by_alias=True)
            await client.post(callback_url, json=payload)
            print(
                f"[DEBUG] Callback sent successfully with keys: {list(payload.keys())}")
        except httpx.HTTPError as http_exc:
            # Log callback failure without affecting main flow
            print(f"[ERROR] Callback failed: {http_exc}")
            print(f"[DEBUG] Callback payload: {callback.model_dump()}")
