"""Hybrid PDF parser combining text extraction and image OCR."""

from __future__ import annotations

from pathlib import Path
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List

from tqdm import tqdm

from .ocr import ocr_image_file


def parse_pdf(pdf_path: str) -> str:
    """Parse a PDF, extracting text and OCR'ing embedded images.

    Parameters
    ----------
    pdf_path:
        Path to the PDF file on disk.

    Returns
    -------
    str
        The resulting Markdown text with optional OCR appendix.
    """

    import pymupdf4llm  # imported lazily for easier testing
    import fitz  # type: ignore

    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    base_md = pymupdf4llm.to_markdown(str(path))

    doc = fitz.open(str(path))
    image_paths: List[Path] = []
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        for page_index, page in enumerate(doc):
            for img_index, img in enumerate(page.get_images(full=True)):
                xref = img[0]
                base_image = doc.extract_image(xref)
                ext = base_image.get("ext", "png")
                img_bytes = base_image["image"]
                img_path = tmp / f"p{page_index}_{img_index}.{ext}"
                img_path.write_bytes(img_bytes)
                image_paths.append(img_path)
        doc.close()

        ocr_texts: List[str] = []
        if image_paths:
            with ThreadPoolExecutor() as executor:
                futures = [executor.submit(ocr_image_file, str(p)) for p in image_paths]
                for future in tqdm(as_completed(futures), total=len(futures)):
                    ocr_texts.append(future.result())

    if ocr_texts:
        appendix = (
            "\n\n---\n\n## 附录：图片内容解析\n\n" + "\n\n---\n\n".join(ocr_texts)
        )
        return base_md + appendix
    return base_md


__all__ = ["parse_pdf"]
