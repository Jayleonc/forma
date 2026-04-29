"""Processor for plain text and markdown files."""

from __future__ import annotations

import logging
from pathlib import Path

from .base import ProcessingResult, Processor

logger = logging.getLogger(__name__)


class TextProcessor(Processor):
    """Pass-through processor for text-like inputs."""

    _ENCODINGS = ("utf-8", "utf-8-sig", "gb18030", "utf-16")

    def process(self, input_path: Path) -> ProcessingResult:
        logger.info("Processing text-like file: %s", input_path)

        raw = input_path.read_bytes()
        content = self._decode(raw)

        return ProcessingResult(
            markdown_content=content,
            text_char_count=len(content),
            image_count=0,
            low_confidence=False,
        )

    @classmethod
    def _decode(cls, raw: bytes) -> str:
        for enc in cls._ENCODINGS:
            try:
                return raw.decode(enc)
            except UnicodeDecodeError:
                continue
        return raw.decode("utf-8", errors="replace")

