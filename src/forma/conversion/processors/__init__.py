"""Document processors for the fast pipeline."""

from .base import ProcessingResult, Processor
from .docx import DocxProcessor
from .image import ImageProcessor
from .pdf import PdfProcessor
from .pptx import PptxProcessor
from .pdf_marker import PdfMarkerProcessor

__all__ = [
    "ProcessingResult",
    "Processor",
    "PdfProcessor",
    "ImageProcessor",
    "DocxProcessor",
    "PptxProcessor",
    "PdfMarkerProcessor",
]
