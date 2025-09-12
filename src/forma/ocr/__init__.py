"""Optical Character Recognition (OCR) Feature Package."""

from .engine import ocr_image_file, parse_image_to_markdown, parse_scanned_pdf
from .client import AdvancedOCRClient

__all__ = [
    "ocr_image_file",
    "parse_image_to_markdown",
    "parse_scanned_pdf",
    "AdvancedOCRClient",
]
