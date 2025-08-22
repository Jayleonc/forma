"""OCR utilities backed by a singleton PaddleOCR engine."""

from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional
import tempfile
from ..shared.utils.device import DEVICE

# NOTE: PyMuPDF (fitz) is only needed for PDF OCR and imported lazily.

_OCR_ENGINE: Optional[Any] = None
_STRUCTURE_ENGINE: Optional[Any] = None


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
            # Handle standard PaddleOCR result format:
            #   [ [ [box_points...], (text, score) ], ... ]
            # item could be a list/tuple of length 2 where the second element is (text, score)
            if (
                isinstance(item, (list, tuple))
                and len(item) == 2
                and isinstance(item[1], (list, tuple))
                and len(item[1]) >= 1
                and isinstance(item[1][0], str)
            ):
                lines.append(item[1][0])
            # Handle RapidOCR result format:
            #   [ [box_points...], text:str, score:float ]
            elif (
                isinstance(item, (list, tuple))
                and len(item) >= 2
                and isinstance(item[1], str)
            ):
                lines.append(item[1])
            else:
                lines.extend(_extract_lines(item))
    return lines


def _get_ocr_engine() -> Any:
    """Return a singleton instance of :class:`PaddleOCR`."""
    global _OCR_ENGINE
    if _OCR_ENGINE is None:
        try:
            from paddleocr import PaddleOCR  # imported lazily for optional dependency

            # Use default OCR pipeline for broad compatibility across versions
            _OCR_ENGINE = PaddleOCR(show_log=False, use_gpu=(DEVICE == "cuda"))
        except Exception:
            # Fallback to RapidOCR (onnxruntime) if PaddleOCR (and deps like cv2) are unavailable.
            class _RapidOCREngine:
                def __init__(self) -> None:
                    from rapidocr_onnxruntime import RapidOCR  # type: ignore

                    self._engine = RapidOCR()

                def ocr(self, image_path: str, cls: bool = True):  # mimic PaddleOCR API
                    res, _ = self._engine(image_path)
                    # Convert to a Paddle-like structure [[box], (text, score)] when possible
                    converted = []
                    for it in res or []:
                        if isinstance(it, (list, tuple)) and len(it) >= 3 and isinstance(it[1], str):
                            converted.append([it[0], (it[1], it[2])])
                        else:
                            converted.append(it)
                    return converted

            _OCR_ENGINE = _RapidOCREngine()
    return _OCR_ENGINE


def _get_structure_engine() -> Any:
    """Return a singleton PP-Structure engine for layout-aware parsing."""
    global _STRUCTURE_ENGINE
    if _STRUCTURE_ENGINE is None:
        try:
            from paddleocr import PPStructure  # type: ignore
        except Exception:  # pragma: no cover - import error path
            # Graceful degrade: return None to allow callers to fallback to plain OCR
            _STRUCTURE_ENGINE = None
            return _STRUCTURE_ENGINE
        _STRUCTURE_ENGINE = PPStructure(
            layout=True, table=True, ocr=True, lang="ch", show_log=False, use_gpu=(DEVICE == "cuda")
        )
    return _STRUCTURE_ENGINE


def ocr_image_file(image_path: str) -> str:
    """Run OCR on a single image and return the extracted text."""
    engine = _get_ocr_engine()
    result = engine.ocr(image_path, cls=True)
    lines = _extract_lines(result)
    return "\n".join(lines)


def parse_image_to_markdown(image_path: str) -> str:
    """Use PP-Structure to parse a single image into Markdown with layout awareness.

    This leverages PaddleOCR's PP-Structure pipeline (layout + table + OCR).
    Falls back to plain text extraction where structured info is unavailable.
    """
    engine = _get_structure_engine()
    if engine is None:
        # PP-Structure unavailable (likely due to missing/deps like OpenCV+NumPy). Fallback.
        return ocr_image_file(image_path)
    blocks: Any = engine(image_path)

    md_parts: List[str] = []
    for block in blocks or []:
        btype = None
        if isinstance(block, dict):
            btype = block.get("type") or (
                isinstance(block.get("layout"),
                           dict) and block["layout"].get("type")
            )
        text = "\n".join(_extract_lines(block)).strip()
        if not text and isinstance(block, dict):
            # Table HTML support if provided by PP-Structure
            res = block.get("res") if isinstance(
                block.get("res"), dict) else None
            html = res.get("html") if res else None
            if html:
                md_parts.append(html)
                continue

        if btype == "title" and text:
            md_parts.append(f"# {text}")
        elif btype == "list" and text:
            # Prefer explicit items from structure result if available; otherwise split lines
            items: List[str] = []
            if isinstance(block, dict):
                candidates = []
                for key in ("items", "children", "res"):
                    val = block.get(key)
                    if isinstance(val, list):
                        candidates.extend(val)
                    elif isinstance(val, dict) and isinstance(val.get("items"), list):
                        candidates.extend(val["items"])  # type: ignore[index]
                for it in candidates:
                    t = "\n".join(_extract_lines(it)).strip()
                    if t:
                        items.append(t)
            if not items:
                # fallback: split merged text by lines
                items = [ln.strip() for ln in text.splitlines() if ln.strip()]
            if items:
                md_parts.append("\n".join(f"* {t}" for t in items))
        elif btype == "table":
            # Prefer structured HTML if available; otherwise keep plain text
            res = block.get("res") if isinstance(
                block.get("res"), dict) else None
            html = res.get("html") if res else None
            md_parts.append(html if html else text)
        else:
            if text:
                md_parts.append(text)

    return "\n\n".join([p for p in md_parts if p])


def parse_scanned_pdf(pdf_path: str) -> str:
    """OCR each page of a scanned PDF by delegating to ``ocr_image_file``."""
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    try:
        import fitz  # type: ignore
    except Exception as e:  # pragma: no cover - import error path
        raise ImportError(
            "PyMuPDF (fitz) is required for PDF OCR. Install with `pip install pymupdf`."
        ) from e

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


__all__ = ["ocr_image_file", "parse_image_to_markdown", "parse_scanned_pdf"]
