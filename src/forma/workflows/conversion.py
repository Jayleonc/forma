"""Workflow module for document conversion.

This was extracted from the previous `controller.py` to separate concerns.
Exposes a single public helper `run_conversion` used by the CLI.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

from ..custom_types import Strategy
from ..core.processors import (
    DocxProcessor,
    ImageProcessor,
    PdfProcessor,
    PptxProcessor,
    Processor,
    ProcessingResult,
)
from ..core.vlm import VlmParser
from ..config import get_vlm_config

THRESHOLD = get_vlm_config().auto_threshold

__all__ = ["run_conversion"]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_conversion(
    inputs: List[Path],
    output_dir: Path,
    strategy: Strategy,
    recursive: bool,
    prompt_name: str = "default_image_description",
    output_name: str | None = None,
) -> None:
    """Entry point invoked by the CLI.

    Parameters
    ----------
    inputs: List[Path]
        Files or directories to process.
    output_dir: Path
        Output directory to place markdown files.
    strategy: Strategy
        Conversion strategy: AUTO | FAST | DEEP
    recursive: bool
        Whether to recurse into sub-directories.
    prompt_name: str, optional
        Prompt name for deep strategy, by default "default_image_description".
    """

    files = _discover_files(inputs, recursive)
    output_dir.mkdir(parents=True, exist_ok=True)
    vlm_parser = VlmParser() if strategy != Strategy.FAST else None
    # If a custom output name is provided and there's only one file, use it.
    # Otherwise, this parameter is ignored.
    effective_output_name = output_name if len(files) == 1 else None

    for path in files:
        _process_single_file(
            path,
            output_dir,
            strategy,
            vlm_parser,
            prompt_name,
            effective_output_name,
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

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
    if suffix == ".pptx":
        return PptxProcessor()
    return None


def _process_single_file(
    path: Path,
    output_dir: Path,
    strategy: Strategy,
    vlm_parser: VlmParser | None = None,
    prompt_name: str = "default_image_description",
    output_name: str | None = None,
) -> None:
    processor = _select_processor(path)
    if processor is None:
        return

    stem = output_name if output_name else path.stem
    output_path = output_dir / f"{stem}.md"

    # For AUTO mode on images, prefer deep strategy directly.
    if strategy == Strategy.AUTO and isinstance(processor, ImageProcessor):
        if not vlm_parser:
            vlm_parser = VlmParser()
        markdown = vlm_parser.parse(path, prompt_name=prompt_name)
        output_path.write_text(markdown, encoding="utf-8")
        return

    if strategy == Strategy.DEEP:
        if not vlm_parser:
            vlm_parser = VlmParser()
        markdown = vlm_parser.parse(path, prompt_name=prompt_name)
        output_path.write_text(markdown, encoding="utf-8")
        return

    result: ProcessingResult = processor.process(path)
    final_md = result.markdown_content

    # For AUTO mode on other file types, use confidence score to decide.
    if strategy == Strategy.AUTO and (
        result.low_confidence or result.text_char_count < THRESHOLD
    ):
        if not vlm_parser:
            vlm_parser = VlmParser()
        final_md = vlm_parser.parse(path, prompt_name=prompt_name)

    output_path.write_text(final_md, encoding="utf-8")
