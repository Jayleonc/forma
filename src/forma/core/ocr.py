"""OCR utilities backed by a singleton PaddleOCR engine."""

from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional
import tempfile

import fitz  # type: ignore

_OCR_ENGINE: Optional[Any] = None


def _extract_lines(data: Any) -> List[str]:
    """Recursively collect all text lines from OCR JSON data."""
    lines: List[str] = []
    if isinstance(data, dict):
        for key, value in data.items():
            if key == "text" and isinstance(value, str):
                lines.append(value)
            else:
                lines.extend(_extract_lines(value))
    elif isinstance(data, list):
        for item in data:
            lines.extend(_extract_lines(item))
    return lines


def _get_ocr_engine() -> Any:
    """Return a singleton instance of :class:`PaddleOCR`."""
    global _OCR_ENGINE
    if _OCR_ENGINE is None:
        from paddleocr import PaddleOCR  # imported lazily for optional dependency

        _OCR_ENGINE = PaddleOCR(structure_version="PP-StructureV3")
    return _OCR_ENGINE


def ocr_image_file(image_path: str) -> str:
    """Run OCR on a single image and return the extracted text."""
    engine = _get_ocr_engine()
    result = engine.ocr(image_path, cls=True)
    lines = _extract_lines(result)
    return "\n".join(lines)


def parse_scanned_pdf(pdf_path: str) -> str:
    """OCR each page of a scanned PDF by delegating to ``ocr_image_file``."""
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    texts: List[str] = []
    doc = fitz.open(str(path))
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        for i, page in enumerate(doc):
            pix = page.get_pixmap()
            img_path = tmp / f"page_{i}.png"
            pix.save(str(img_path))
            texts.append(ocr_image_file(str(img_path)))
    doc.close()
    return "\n".join(texts)


__all__ = ["ocr_image_file", "parse_scanned_pdf"]

