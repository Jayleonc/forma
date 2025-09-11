"""Processor for PPTX files."""

from __future__ import annotations

import os
import time
import tempfile
from pathlib import Path
from typing import List, Optional

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE

from ...shared.utils.retry import retry

from .base import Processor, ProcessingResult
from ...ocr import parse_image_to_markdown, AdvancedOCRClient
from ...vision import VlmParser, VLMClient
from ...shared.utils.converters import convert_to_pdf
from ...shared.config import get_ocr_config
import fitz  # PyMuPDF


class PptxProcessor(Processor):
    """Processor for PPTX files with slide-wise heuristics."""

    COMPLEX_THRESHOLD = 25
    
    def __init__(self, vlm_client: Optional[VLMClient] = None, advanced_ocr_client: Optional[AdvancedOCRClient] = None) -> None:
        """Initialize the PPTX processor.
        
        Args:
            vlm_client: Optional VLM client for image description
            advanced_ocr_client: Optional advanced OCR client for text recognition
        """
        self._vlm_client = vlm_client
        
        # 尝试创建高级OCR客户端
        self._advanced_ocr_client = advanced_ocr_client
        if self._advanced_ocr_client is None:
            try:
                config = get_ocr_config()
                self._advanced_ocr_client = AdvancedOCRClient(
                    api_key=config.api_key,
                    model=config.model,
                    base_url=config.base_url,
                    max_file_size=config.max_file_size
                )
                print(f"[DEBUG] PptxProcessor: Advanced OCR client initialized with model {config.model}")
            except Exception as e:
                print(f"[WARNING] PptxProcessor: Failed to initialize Advanced OCR client: {e}")
                self._advanced_ocr_client = None

    def _parse_with_retry(self, image_path: Path, slide_idx: int) -> str:
        """使用重试机制调用VLM服务解析幻灯片"""
        
        @retry(max_tries=3, delay=1.0, backoff=2.0, 
               exceptions=(Exception,),
               on_retry=lambda e, i: print(f"[WARNING] PptxProcessor: VLM retry {i}/3 for slide {slide_idx+1} due to: {e}"))
        def _parse(path):
            from ...vision import VlmParser
            vlm = VlmParser(self._vlm_client)
            return vlm.parse(path)
        
        return _parse(image_path)
    
    def _recognize_text_with_retry(self, image_path: Path, slide_idx: int) -> str:
        """使用重试机制调用高级OCR服务识别图片文字"""
        
        @retry(max_tries=3, delay=1.0, backoff=2.0, 
               exceptions=(Exception,),
               on_retry=lambda e, i: print(f"[WARNING] PptxProcessor: GOT-OCR2_0 retry {i}/3 for slide {slide_idx+1} due to: {e}"))
        def _recognize(path):
            return self._advanced_ocr_client.recognize_text(path)
        
        return _recognize(image_path)
    
    def process(self, input_path: Path) -> ProcessingResult:
        """处理PPTX文件，返回处理结果"""
        process_start_time = time.time()
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
                    vlm = VlmParser(self._vlm_client)

                    for idx in complex_indices:
                        if not (0 <= idx < len(doc)):
                            slide_markdowns[idx] = f"> _[警告] 幻灯片索引 {idx + 1} 超出范围。_"
                            continue
                        
                        page = doc.load_page(idx)
                        pix = page.get_pixmap(dpi=200)
                        img_path = tmp / f"complex_slide_{idx}.png"
                        pix.save(str(img_path))
                        
                        # 先使用原有的图像分析方法进行预处理
                        # 然后优先使用高级OCR（GOT-OCR2_0），失败时使用VLM兜底
                        final_markdown = ""
                        file_size = os.path.getsize(img_path)
                        
                        # 优先使用VLM处理幻灯片内容
                        if self._vlm_client:
                            start_time = time.time()
                            try:
                                print(f"[DEBUG] PptxProcessor: Processing slide {idx+1} with VLM")
                                vlm_markdown = self._parse_with_retry(img_path, idx)
                                # 检查VLM结果质量，如果结果过短，则不认为成功
                                if vlm_markdown.strip() and len(vlm_markdown.strip()) >= 20:  # 至少20个字符才认为有效
                                    final_markdown = vlm_markdown
                                    elapsed = time.time() - start_time
                                    print(f"[DEBUG] PptxProcessor: VLM completed for slide {idx+1}, text length: {len(vlm_markdown)}, took {elapsed:.2f}s")
                                else:
                                    print(f"[WARNING] PptxProcessor: VLM result too short for slide {idx+1}, length: {len(vlm_markdown.strip() if vlm_markdown else '')}, falling back to OCR")
                            except Exception as e:
                                print(f"[ERROR] PptxProcessor: VLM failed for slide {idx+1} after retries: {e}")
                        
                        # 如果VLM失败或返回空结果，使用高级OCR（GOT-OCR2_0）兜底
                        if not final_markdown and self._advanced_ocr_client:
                            start_time = time.time()
                            try:
                                print(f"[DEBUG] PptxProcessor: Processing slide {idx+1} with GOT-OCR2_0 (file size: {file_size} bytes)")
                                ocr_text = self._recognize_text_with_retry(img_path, idx)
                                if ocr_text.strip():  # 只保留非空结果
                                    final_markdown = ocr_text
                                    elapsed = time.time() - start_time
                                    print(f"[DEBUG] PptxProcessor: GOT-OCR2_0 completed for slide {idx+1}, text length: {len(ocr_text)}, took {elapsed:.2f}s")
                                else:
                                    print(f"[DEBUG] PptxProcessor: GOT-OCR2_0 returned empty result for slide {idx+1}")
                            except ValueError as e:
                                # 文件大小超限或其他值错误
                                print(f"[WARNING] PptxProcessor: GOT-OCR2_0 skipped for slide {idx+1}: {e}")
                            except Exception as e:
                                # 其他错误
                                print(f"[ERROR] PptxProcessor: GOT-OCR2_0 failed for slide {idx+1} after retries: {e}")
                        # 已在前面优先使用VLM，这里不需要重复
                        
                        # 如果GOT-OCR2_0和VLM都失败，使用快速路径文本
                        if not final_markdown:
                            fast_path_text = complex_slide_texts.get(idx, "")
                            if fast_path_text:
                                final_markdown = fast_path_text
                                print(f"[DEBUG] PptxProcessor: Using fast-path text for slide {idx+1}, length: {len(fast_path_text)}")
                            else:
                                final_markdown = "> _[提示] 无法解析此幻灯片内容。_"
                                print(f"[WARNING] PptxProcessor: No content extracted for slide {idx+1}")
                        else:
                            # 如果有快速路径文本，并且与最终结果不重复，则合并
                            fast_path_text = complex_slide_texts.get(idx, "")
                            if fast_path_text and fast_path_text not in final_markdown:
                                final_markdown = f"{fast_path_text}\n\n{final_markdown}"
                        
                        slide_markdowns[idx] = final_markdown
                        image_count += 1
                        print(f"[DEBUG] PptxProcessor: Completed processing slide {idx+1}")

                    doc.close()

                except (RuntimeError, FileNotFoundError) as e:
                    # If conversion or parsing fails, provide a general message
                    # and leave the complex slide markdown empty or with a notice.
                    error_msg = (
                        f"> _[提示] 深度解析失败: {e}_\n"
                        f"> _请确保已正确安装 LibreOffice。_"
                    )
                    print(f"[ERROR] PptxProcessor: Deep parsing failed: {e}")
                    for idx in complex_indices:
                        if not slide_markdowns[idx]: # Avoid overwriting fallback text
                            slide_markdowns[idx] = error_msg

        markdown = "\n\n---\n\n".join(m for m in slide_markdowns if m)
        text_len = len(markdown.strip())
        total_elapsed = time.time() - process_start_time
        print(f"[DEBUG] PptxProcessor: Processing completed in {total_elapsed:.2f}s")
        
        return ProcessingResult(
            markdown_content=markdown,
            text_char_count=text_len,
            image_count=image_count,
            low_confidence=text_len == 0,
        )


__all__ = ["PptxProcessor"]
