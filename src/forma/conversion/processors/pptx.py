"""Processor for PPTX files."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import List

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE

from .base import Processor, ProcessingResult
from ...ocr import parse_image_to_markdown
from ...vision import VlmParser
from ...shared.utils.converters import convert_to_pdf
import fitz  # PyMuPDF


class PptxProcessor(Processor):
    """Processor for PPTX files with slide-wise heuristics."""

    COMPLEX_THRESHOLD = 25

    def process(self, input_path: Path) -> ProcessingResult:
        from pptx import Presentation
        from pptx.enum.shapes import MSO_SHAPE_TYPE

        # MSO_SHAPE_TYPE.SMART_ART is 24, but might not be in older pptx versions
        MSO_SHAPE_TYPE_SMART_ART = getattr(MSO_SHAPE_TYPE, "SMART_ART", 24)

        path = Path(input_path)
        pres = Presentation(str(path))
        slide_count = len(pres.slides)
        # placeholders for ordered markdown output
        slide_markdowns: List[str] = ["" for _ in range(slide_count)]
        complex_slide_texts: dict[int, str] = {}
        complex_indices: List[int] = []
        image_count = 0

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            # First pass: extract content and decide slide complexity
            for idx, slide in enumerate(pres.slides):
                texts: List[str] = []
                images: List[Path] = []
                is_complex_shape_found = False

                for shape in slide.shapes:
                    # Rule 1: Detect complex shapes that require visual rendering
                    if shape.shape_type in [
                        MSO_SHAPE_TYPE.CHART,
                        MSO_SHAPE_TYPE_SMART_ART,
                        MSO_SHAPE_TYPE.TABLE,  # Tables can be complex
                    ]:
                        is_complex_shape_found = True
                        break

                    if getattr(shape, "has_text_frame", False) and shape.text.strip():
                        texts.append(shape.text.strip())

                    if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
                        image = shape.image
                        ext = image.ext or "png"
                        img_path = tmp / f"slide{idx}_{len(images)}.{ext}"
                        img_path.write_bytes(image.blob)
                        images.append(img_path)

                slide_text = "\n".join(texts)
                char_count = len(slide_text.replace("\n", "").strip())

                # Rule 2: Slides with very little text are also considered complex
                is_complex = is_complex_shape_found or (char_count < self.COMPLEX_THRESHOLD)

                if is_complex:
                    complex_indices.append(idx)
                    # Store the extracted text for later merging
                    complex_slide_texts[idx] = slide_text
                    # We still process images on complex slides for OCR, just in case
                    # VLM fails or for a more complete picture.

                # All slides (simple and complex) can have images that need OCR
                ocr_texts = [parse_image_to_markdown(str(p)) for p in images]
                if ocr_texts:
                    slide_text = (
                        slide_text + "\n\n" + "\n\n".join(ocr_texts)
                    ).strip()
                
                if not is_complex:
                    # This is a content slide, process with fast path
                    slide_markdowns[idx] = slide_text
                
                image_count += len(images)

            # Deep path for complex slides, optimized for single conversion
            if complex_indices:
                pdf_path = None
                try:
                    # Convert the entire PPTX to PDF once
                    pdf_path = convert_to_pdf(input_path=path, output_dir=tmp)
                    doc = fitz.open(str(pdf_path))
                    vlm = VlmParser()

                    for idx in complex_indices:
                        if not (0 <= idx < len(doc)):
                            slide_markdowns[idx] = f"> _[警告] 幻灯片索引 {idx + 1} 超出范围。_"
                            continue
                        
                        page = doc.load_page(idx)
                        pix = page.get_pixmap(dpi=200)
                        img_path = tmp / f"complex_slide_{idx}.png"
                        pix.save(str(img_path))
                        
                        vlm_markdown = vlm.parse(img_path)
                        
                        # Hybrid Parsing: Combine fast-path text with VLM analysis
                        fast_path_text = complex_slide_texts.get(idx, "")
                        
                        # Combine results, ensuring no duplication if text is similar
                        # A simple combination strategy for now:
                        final_markdown = vlm_markdown
                        if fast_path_text and fast_path_text not in vlm_markdown:
                            final_markdown = f"{fast_path_text}\n\n{vlm_markdown}"
                        
                        slide_markdowns[idx] = final_markdown
                        image_count += 1

                    doc.close()

                except (RuntimeError, FileNotFoundError) as e:
                    # If conversion or parsing fails, provide a general message
                    # and leave the complex slide markdown empty or with a notice.
                    error_msg = (
                        f"> _[提示] 深度解析失败: {e}_\n"
                        f"> _请确保已正确安装 LibreOffice。_"
                    )
                    for idx in complex_indices:
                        if not slide_markdowns[idx]: # Avoid overwriting fallback text
                            slide_markdowns[idx] = error_msg

        markdown = "\n\n---\n\n".join(m for m in slide_markdowns if m)
        text_len = len(markdown.strip())
        return ProcessingResult(
            markdown_content=markdown,
            text_char_count=text_len,
            image_count=image_count,
            low_confidence=text_len == 0,
        )


__all__ = ["PptxProcessor"]
