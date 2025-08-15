from __future__ import annotations

from pathlib import Path
import importlib
from typing import Any, List


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


def parse_scanned_pdf(pdf_path: str) -> str:
    """Perform OCR on a scanned PDF and return Markdown text."""
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    try:
        module = importlib.import_module("paddleocr_json.paddleocr_json")
        PaddleOCR = getattr(module, "PaddleOCR")
    except Exception as exc:  # pragma: no cover - depends on external package
        raise RuntimeError("paddleocr-json is required for OCR parsing") from exc

    ocr = PaddleOCR()
    result = ocr.ocr(str(path))
    lines = _extract_lines(result)
    return "\n".join(lines)
