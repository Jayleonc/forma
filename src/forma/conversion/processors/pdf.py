"""Processor for PDF files."""

from __future__ import annotations

import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List

import fitz
import pymupdf4llm

from .base import ProcessingResult, Processor
from ...ocr import ocr_image_file


class PdfProcessor(Processor):
    """Processor for PDF files using PyMuPDF and OCR."""

    def process(self, input_path: Path) -> ProcessingResult:
        print(f"[DEBUG] PdfProcessor: Starting to process {input_path}")
        path = Path(input_path)
        
        try:
            print(f"[DEBUG] PdfProcessor: Converting PDF to markdown with pymupdf4llm")
            base_md = pymupdf4llm.to_markdown(str(path))
            text_len = len(base_md.strip())
            print(f"[DEBUG] PdfProcessor: Base markdown extracted, length: {text_len} characters")
        except Exception as e:
            print(f"[ERROR] PdfProcessor: Failed to convert PDF to markdown: {e.__class__.__name__}: {e}")
            raise

        try:
            print(f"[DEBUG] PdfProcessor: Opening PDF with fitz (PyMuPDF)")
            doc = fitz.open(str(path))
            print(f"[DEBUG] PdfProcessor: PDF opened successfully, pages: {len(doc)}")
            
            image_paths: List[Path] = []
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp = Path(tmpdir)
                print(f"[DEBUG] PdfProcessor: Created temp directory: {tmp}")
                
                for page_index, page in enumerate(doc):
                    images = page.get_images(full=True)
                    print(f"[DEBUG] PdfProcessor: Page {page_index+1}/{len(doc)} has {len(images)} images")
                    
                    for img_index, img in enumerate(images):
                        xref = img[0]
                        print(f"[DEBUG] PdfProcessor: Extracting image {img_index+1}/{len(images)} from page {page_index+1}")
                        base_image = doc.extract_image(xref)
                        ext = base_image.get("ext", "png")
                        img_bytes = base_image["image"]
                        img_path = tmp / f"p{page_index}_{img_index}.{ext}"
                        img_path.write_bytes(img_bytes)
                        image_paths.append(img_path)
                        print(f"[DEBUG] PdfProcessor: Saved image to {img_path}")
                
                print(f"[DEBUG] PdfProcessor: Closing PDF document")
                doc.close()
                print(f"[DEBUG] PdfProcessor: Extracted {len(image_paths)} images total")

                ocr_texts: List[str] = []
                if image_paths:
                    print(f"[DEBUG] PdfProcessor: Starting OCR on {len(image_paths)} images")
                    with ThreadPoolExecutor() as executor:
                        futures = [
                            executor.submit(ocr_image_file, str(p))
                            for p in image_paths
                        ]
                        for i, future in enumerate(as_completed(futures)):
                            try:
                                result = future.result()
                                ocr_texts.append(result)
                                print(f"[DEBUG] PdfProcessor: OCR completed for image {i+1}/{len(image_paths)}, text length: {len(result)}")
                            except Exception as e:
                                print(f"[ERROR] PdfProcessor: OCR failed for an image: {e.__class__.__name__}: {e}")
        except Exception as e:
            print(f"[ERROR] PdfProcessor: Error processing PDF: {e.__class__.__name__}: {e}")
            raise

        print(f"[DEBUG] PdfProcessor: Finalizing markdown content")
        markdown = base_md
        if ocr_texts:
            print(f"[DEBUG] PdfProcessor: Adding OCR results from {len(ocr_texts)} images to markdown")
            appendix = (
                "\n\n---\n\n## 附录：图片内容解析\n\n" + "\n\n---\n\n".join(ocr_texts)
            )
            markdown += appendix
            print(f"[DEBUG] PdfProcessor: Final markdown length with OCR: {len(markdown)} characters")
        else:
            print(f"[DEBUG] PdfProcessor: No OCR text to add, final markdown length: {len(markdown)} characters")

        low_conf = text_len < 50
        print(f"[DEBUG] PdfProcessor: Confidence assessment: {'LOW' if low_conf else 'HIGH'} (text length: {text_len})")
        
        result = ProcessingResult(
            markdown_content=markdown,
            text_char_count=text_len,
            image_count=len(image_paths),
            low_confidence=low_conf,
        )
        print(f"[DEBUG] PdfProcessor: Processing completed successfully")
        return result

__all__ = ["PdfProcessor"]
