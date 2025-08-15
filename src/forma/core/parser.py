from __future__ import annotations

from pathlib import Path
import importlib
from typing import Any


def parse_text_pdf(pdf_path: str) -> str:
    """Convert a text-based PDF to Markdown.

    Parameters
    ----------
    pdf_path:
        Path to the PDF file on disk.

    Returns
    -------
    str
        The resulting Markdown text.

    Raises
    ------
    FileNotFoundError
        If the provided path does not exist.
    RuntimeError
        If conversion fails for any reason.
    """

    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    try:
        pymupdf4llm: Any = importlib.import_module("pymupdf4llm")
    except ImportError as exc:  # pragma: no cover - depends on external package
        raise RuntimeError("pymupdf4llm is required to parse PDFs") from exc

    try:
        return pymupdf4llm.to_markdown(str(path))
    except Exception as exc:  # pragma: no cover - depends on external package
        raise RuntimeError(f"Failed to parse PDF: {pdf_path}") from exc
