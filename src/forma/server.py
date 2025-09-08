"""Async callback-driven FastAPI server for forma."""

from __future__ import annotations

import asyncio
import tempfile
import uuid
from pathlib import Path

import httpx
from fastapi import FastAPI, status
from pydantic import BaseModel, HttpUrl
import contextlib

from .conversion.workflow import run_conversion
from .shared.custom_types import Strategy


class ConvertRequest(BaseModel):
    request_id: str
    source_url: HttpUrl
    callback_url: HttpUrl


class ConvertResponse(BaseModel):
    task_id: str
    status: str = "processing"


class CallbackPayload(BaseModel):
    request_id: str
    status: str
    markdown_content: str | None = None
    error_message: str | None = None


class ConversionTask(BaseModel):
    task_id: str
    request_id: str
    source_url: str
    callback_url: str


app = FastAPI()
queue: asyncio.Queue[ConversionTask] = asyncio.Queue()


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

    callback = CallbackPayload(request_id=task.request_id, status="failed")
    try:
        with tempfile.TemporaryDirectory() as temp_dir_str:
            temp_dir = Path(temp_dir_str)
            input_path = temp_dir / "input"

            resp = await client.get(task.source_url)
            resp.raise_for_status()
            input_path.write_bytes(resp.content)

            output_dir = temp_dir / "output"
            output_dir.mkdir()

            run_conversion(
                inputs=[input_path],
                output_dir=output_dir,
                strategy=Strategy.AUTO,
                recursive=False,
            )

            output_files = list(output_dir.glob("*.md"))
            if not output_files:
                raise RuntimeError("Conversion produced no output")
            markdown = output_files[0].read_text(encoding="utf-8")
            callback.status = "completed"
            callback.markdown_content = markdown
    except Exception as exc:  # pragma: no cover - best effort logging
        callback.error_message = str(exc)
    finally:
        try:
            await client.post(task.callback_url, json=callback.model_dump())
        except httpx.HTTPError:
            pass


