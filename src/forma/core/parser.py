"""Hybrid PDF parser combining text extraction and image OCR."""

from __future__ import annotations

from pathlib import Path

from ..ocr import ocr_image_file

def parse_pdf(pdf_path: str) -> str:
    """Compatibility wrapper around :class:`PdfProcessor`.

    This function mirrors the behaviour of the original ``parse_pdf`` utility
    so that existing callers (including tests) can continue to work while the
    new processor based architecture is adopted.
    """

    from ..conversion.processors import PdfProcessor

    processor = PdfProcessor()
    result = processor.process(Path(pdf_path))
    return result.markdown_content


__all__ = ["parse_pdf", "ocr_image_file"]
