"""Processor for PDF files."""

from __future__ import annotations

import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List

import fitz
import pymupdf4llm

from .base import ProcessingResult, Processor
from .. import parser as _parser


class PdfProcessor(Processor):
    """Processor for PDF files using PyMuPDF and OCR."""

    def process(self, input_path: Path) -> ProcessingResult:
        path = Path(input_path)
        base_md = pymupdf4llm.to_markdown(str(path))
        text_len = len(base_md.strip())

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
                    futures = [
                        executor.submit(_parser.ocr_image_file, str(p))
                        for p in image_paths
                    ]
                    for future in as_completed(futures):
                        ocr_texts.append(future.result())

        markdown = base_md
        if ocr_texts:
            appendix = (
                "\n\n---\n\n## 附录：图片内容解析\n\n" + "\n\n---\n\n".join(ocr_texts)
            )
            markdown += appendix

        low_conf = text_len < 50
        return ProcessingResult(
            markdown_content=markdown,
            text_char_count=text_len,
            image_count=len(image_paths),
            low_confidence=low_conf,
        )

__all__ = ["PdfProcessor"]
