"""Core orchestration logic for document conversion."""

from __future__ import annotations

from pathlib import Path
from typing import List

from .types import Strategy
from .core.processors import (
    DocxProcessor,
    ImageProcessor,
    PdfProcessor,
    Processor,
    ProcessingResult,
)
from .core.vlm import VlmParser

THRESHOLD = 200  # minimal characters before escalating to VLM


def run_conversion(
    inputs: List[Path],
    output_dir: Path,
    strategy: Strategy,
    recursive: bool,
) -> None:
    """Entry point invoked by the CLI."""

    files = _discover_files(inputs, recursive)
    output_dir.mkdir(parents=True, exist_ok=True)
    vlm_parser = None if strategy == Strategy.FAST else VlmParser()
    for path in files:
        _process_single_file(path, output_dir, strategy, vlm_parser)


def _discover_files(inputs: List[Path], recursive: bool) -> List[Path]:
    files: List[Path] = []
    for inp in inputs:
        if inp.is_file():
            files.append(inp)
        elif inp.is_dir():
            iterator = inp.rglob("*") if recursive else inp.glob("*")
            for p in iterator:
                if p.is_file():
                    files.append(p)
    return files


def _select_processor(path: Path) -> Processor | None:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return PdfProcessor()
    if suffix in {".png", ".jpg", ".jpeg", ".bmp"}:
        return ImageProcessor()
    if suffix == ".docx":
        return DocxProcessor()
    return None


def _process_single_file(
    path: Path,
    output_dir: Path,
    strategy: Strategy,
    vlm_parser: VlmParser | None = None,
) -> None:
    processor = _select_processor(path)
    if processor is None:
        return

    output_path = output_dir / f"{path.stem}.md"

    if strategy == Strategy.DEEP:
        parser = vlm_parser or VlmParser()
        markdown = parser.parse(path, prompt="请详细描述图片的内容，包括标题、正文和具体的内容，无关的字符除外")
        output_path.write_text(markdown, encoding="utf-8")
        return

    result: ProcessingResult = processor.process(path)
    final_md = result.markdown_content

    if strategy == Strategy.AUTO:
        if result.low_confidence or result.text_char_count < THRESHOLD:
            parser = vlm_parser or VlmParser()
            final_md = parser.parse(path, prompt="请详细描述图片的内容，包括标题、正文和具体的内容，无关的字符除外")

    output_path.write_text(final_md, encoding="utf-8")


__all__ = ["run_conversion"]
