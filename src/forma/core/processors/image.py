"""Processor for image files."""

from __future__ import annotations

from pathlib import Path

from .base import ProcessingResult, Processor
from ..ocr import parse_image_to_markdown


class ImageProcessor(Processor):
    """Processor for image files using OCR."""

    def process(self, input_path: Path) -> ProcessingResult:
        md = parse_image_to_markdown(str(input_path))
        text_len = len(md.strip())
        return ProcessingResult(
            markdown_content=md,
            text_char_count=text_len,
            image_count=1,
            low_confidence=text_len == 0,
        )

__all__ = ["ImageProcessor"]
