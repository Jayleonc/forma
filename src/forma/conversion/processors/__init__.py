"""Document processors for the fast pipeline."""

from __future__ import annotations

from .base import ExtractedVisualAsset, ProcessingResult, Processor

_PROCESSOR_MODULES = {
    "DocxProcessor": ".docx",
    "ImageProcessor": ".image",
    "PdfProcessor": ".pdf",
    "PptxProcessor": ".pptx",
    "PdfMarkerProcessor": ".pdf_marker",
    "XlsxProcessor": ".xlsx",
    "TextProcessor": ".text",
}


def __getattr__(name: str):
    module_name = _PROCESSOR_MODULES.get(name)
    if module_name is None:
        raise AttributeError(name)

    from importlib import import_module

    module = import_module(module_name, __name__)
    value = getattr(module, name)
    globals()[name] = value
    return value


__all__ = [
    "ExtractedVisualAsset",
    "ProcessingResult",
    "Processor",
    "PdfProcessor",
    "ImageProcessor",
    "DocxProcessor",
    "PptxProcessor",
    "PdfMarkerProcessor",
    "XlsxProcessor",
    "TextProcessor",
]
