"""Async callback-driven FastAPI server for forma."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
import time
import uuid
from pathlib import Path

import httpx
from fastapi import FastAPI, status, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, AnyHttpUrl, ConfigDict
import contextlib

from .conversion.workflow import run_conversion
from .shared.custom_types import Strategy


logger = logging.getLogger(__name__)
CONVERSION_TIMEOUT = float(os.getenv("FORMA_CONVERSION_TIMEOUT", "600"))
QA_TIMEOUT = float(os.getenv("FORMA_QA_TIMEOUT", "600"))
DATA_DIR = Path(os.getenv("FORMA_DATA_DIR", "./data"))

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
    logger.error("Request validation failed: %s", exc.errors())
    # Body may be bytes; limit size to avoid noisy logs
    preview = body[:2048]
    logger.debug("Raw request body preview (up to 2KB): %r", preview)
    return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content={"detail": exc.errors()})


@app.on_event("startup")
async def start_worker() -> None:
    logger.debug("Starting workers...")
    try:
        # 启动多个 conversion worker
        num_conversion_workers = int(os.environ.get("CONVERSION_WORKERS", 4))
        logger.debug("Creating %s conversion workers", num_conversion_workers)
        app.state.conversion_workers = [
            asyncio.create_task(conversion_worker(worker_id=i))
            for i in range(num_conversion_workers)
        ]
        logger.info("Started %s conversion workers.", num_conversion_workers)

        # 启动多个 QA worker
        num_qa_workers = int(os.environ.get("QA_WORKERS", 2))
        logger.debug("Creating %s QA workers", num_qa_workers)
        app.state.qa_workers = [
            asyncio.create_task(qa_worker(worker_id=i))
            for i in range(num_qa_workers)
        ]
        logger.info("Started %s QA workers.", num_qa_workers)
    except Exception:
        logger.exception("Error starting workers")


@app.on_event("shutdown")
async def stop_worker() -> None:
    logger.debug("Shutting down workers...")
    try:
        # 取消所有 worker 任务
        logger.debug("Cancelling conversion workers...")
        if hasattr(app.state, 'conversion_workers'):
            for worker in app.state.conversion_workers:
                worker.cancel()
        else:
            logger.warning("No conversion_workers found in app.state")

        logger.debug("Cancelling QA workers...")
        if hasattr(app.state, 'qa_workers'):
            for worker in app.state.qa_workers:
                worker.cancel()
        else:
            logger.warning("No qa_workers found in app.state")

        # 等待所有 worker 任务完成取消
        logger.debug("Waiting for conversion workers to complete cancellation...")
        if hasattr(app.state, 'conversion_workers'):
            for worker in app.state.conversion_workers:
                with contextlib.suppress(asyncio.CancelledError):
                    await worker

        logger.debug("Waiting for QA workers to complete cancellation...")
        if hasattr(app.state, 'qa_workers'):
            for worker in app.state.qa_workers:
                with contextlib.suppress(asyncio.CancelledError):
                    await worker

        logger.info("All workers have been shut down.")
    except Exception:
        logger.exception("Error shutting down workers")


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
            logger.debug(
                "Conversion worker %s picked up task: %s", worker_id, task.task_id)
            try:
                await process_conversion_task(task, client)
            finally:
                conversion_queue.task_done()


async def qa_worker(worker_id: int) -> None:
    """Background worker that processes FAQ generation tasks."""

    async with httpx.AsyncClient(timeout=None) as client:
        while True:
            task = await qa_queue.get()
            logger.debug(
                "QA worker %s picked up task: %s", worker_id, task.task_id)
            try:
                await process_qa_task(task, client)
            finally:
                qa_queue.task_done()


async def process_qa_task(task: GenerateQATask, client: httpx.AsyncClient) -> None:
    """Process FAQ generation task and callback the result."""

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
                    await asyncio.wait_for(
                        asyncio.to_thread(
                            run_knowledge_pipeline,
                            input_path=input_path,
                            output_dir=output_dir,
                            export_csv=False,
                        ),
                        timeout=QA_TIMEOUT,
                    )
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
        try:
            callback_url = str(task.callback_url)
            logger.debug(
                "Sending callback to %s, status: %s", callback_url, callback.status
            )

            payload = callback.model_dump(by_alias=True)
            await client.post(callback_url, json=payload)
            logger.debug(
                "Callback sent successfully with keys: %s", list(payload.keys())
            )
        except httpx.HTTPError as http_exc:
            logger.error("Callback failed: %s", http_exc)
            logger.debug("Callback payload: %s", callback.model_dump())


async def process_conversion_task(task: ConversionTask, client: httpx.AsyncClient) -> None:
    """Download, convert and callback the result."""

    callback = CallbackPayload(request_id=task.request_id, status="failed")
    input_path: Path | None = None
    try:
        logger.debug(
            "Task received: %s (request_id=%s, source_url=%s)",
            task.task_id,
            task.request_id,
            task.source_url,
        )

        with tempfile.TemporaryDirectory() as temp_dir_str:
            temp_dir = Path(temp_dir_str)

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
                    await asyncio.wait_for(
                        asyncio.to_thread(
                            run_conversion,
                            inputs=[input_path],
                            output_dir=output_dir,
                            strategy=Strategy.AUTO,
                            recursive=False,
                            use_ocr_for_images=False,
                        ),
                        timeout=CONVERSION_TIMEOUT,
                    )
                    logger.debug("Conversion completed successfully")

                except asyncio.TimeoutError:
                    logger.warning(
                        "Conversion timed out after %s seconds for %s",
                        CONVERSION_TIMEOUT,
                        input_path.name,
                    )
                    logger.debug("Attempting fallback processing method")

                    from .conversion.workflow import process_fallback
                    from .conversion.workflow import _select_processor
                    from .vision import OpenAIVLMClient, VlmParser

                    vlm_client = OpenAIVLMClient()
                    vlm_parser = VlmParser(vlm_client)

                    processor = _select_processor(input_path, vlm_client)
                    if processor is None:
                        raise RuntimeError(
                            f"No suitable processor found for {input_path}"
                        )

                    logger.debug("Using fallback processing for %s", input_path)
                    final_md, _ = await asyncio.to_thread(
                        process_fallback,
                        processor=processor,
                        path=input_path,
                        vlm_client=vlm_client,
                        vlm_parser=vlm_parser,
                        prompt_name="default_image_description",
                    )

                    from .shared.utils.markdown_cleaner import MarkdownCleaner

                    cleaned_md = MarkdownCleaner.clean_markdown(final_md)
                    output_file = output_dir / f"{input_path.stem}.md"
                    output_file.write_text(cleaned_md, encoding="utf-8")
                    logger.debug(
                        "Fallback processing completed and saved to %s",
                        output_file,
                    )

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
            callback.status = "completed"
            callback.markdown_content = markdown
            logger.debug(
                "Successfully read markdown content, length: %s characters",
                len(markdown),
            )
    except Exception as exc:
        import traceback

        tb_str = traceback.format_exc(limit=5)
        file_info = (
            f"File: {Path(str(task.source_url)).name}" if input_path else "Unknown file"
        )
        callback.error_message = (
            f"{file_info} - {exc.__class__.__name__}: {exc}\n{tb_str}"
        )
        logger.error(
            "Task processing failed: %s: %s", exc.__class__.__name__, exc
        )
    finally:
        try:
            callback_url = str(task.callback_url)
            logger.debug(
                "Sending callback to %s, status: %s", callback_url, callback.status
            )

            payload = callback.model_dump(by_alias=True)
            await client.post(callback_url, json=payload)
            logger.debug(
                "Callback sent successfully with keys: %s", list(payload.keys())
            )
        except httpx.HTTPError as http_exc:
            logger.error("Callback failed: %s", http_exc)
            logger.debug("Callback payload: %s", callback.model_dump())
