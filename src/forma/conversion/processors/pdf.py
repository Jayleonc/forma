"""Processor for PDF files."""

from __future__ import annotations

import logging
import fitz
import os
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pymupdf4llm

from ...shared.utils.retry import retry
from .batch_processor import BatchProcessor

from ...ocr import ocr_image_file, AdvancedOCRClient
from ...vision import VLMClient
from ...shared.config import get_ocr_config
from .base import ProcessingResult, Processor


logger = logging.getLogger(__name__)


class PdfProcessor(Processor):
    """PDF处理器，用于将PDF文件转换为Markdown格式"""

    def __init__(
        self,
        vlm_client: Optional[VLMClient] = None,
        use_ocr: bool = False,
        min_text_chars: int = 8,
        advanced_ocr_client: Optional[AdvancedOCRClient] = None,
        use_advanced_ocr: bool = False,
    ):
        """初始化PDF处理器

        Args:
            vlm_client: VLM客户端，用于处理图片
            use_ocr: 是否仅使用OCR而不是VLM
            min_text_chars: OCR文本最小字符数阈值
            ocr_client: OCR客户端，用于处理图片文字识别，如果为None则尝试创建
        """
        self._vlm_client = vlm_client
        self._use_ocr = use_ocr
        self._min_text_chars = min_text_chars
        self._use_advanced_ocr = use_advanced_ocr

        # 仅在开启开关时才尝试创建高级OCR客户端
        self._advanced_ocr_client = None
        if self._use_advanced_ocr:
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
                    logger.debug(
                        "PdfProcessor: Advanced OCR client initialized with model %s",
                        config.model,
                    )
                except Exception as e:
                    logger.warning(
                        "PdfProcessor: Failed to initialize Advanced OCR client: %s",
                        e,
                    )
                    self._advanced_ocr_client = None

    def _describe_with_retry(self, image_path: Path, image_index: int) -> str:
        """使用重试机制调用VLM服务描述图片"""
        
        @retry(
            max_tries=3,
            delay=1.0,
            backoff=2.0,
            exceptions=(Exception,),
            on_retry=lambda e, i: logger.warning(
                "PdfProcessor: VLM retry %s/3 for image %s due to: %s",
                i,
                image_index,
                e,
            ),
        )
        def _describe(path, prompt):
            return self._vlm_client.describe(path, prompt_name=prompt)
        
        return _describe(image_path, "pdf_image_description")
    
    def _recognize_text_with_retry(self, image_path: Path, image_index: int) -> str:
        """使用重试机制调用高级OCR服务识别图片文字"""
        
        @retry(
            max_tries=3,
            delay=1.0,
            backoff=2.0,
            exceptions=(Exception,),
            on_retry=lambda e, i: logger.warning(
                "PdfProcessor: GOT-OCR2_0 retry %s/3 for image %s due to: %s",
                i,
                image_index,
                e,
            ),
        )
        def _recognize(path):
            return self._advanced_ocr_client.recognize_text(path)
        
        return _recognize(image_path)
    
    def _fallback_extract_markdown(self, path: Path) -> str:
        """当 pymupdf4llm 失败时的备用提取方法，逐页使用 PyMuPDF 提取文本"""
        doc = fitz.open(str(path))
        parts: List[str] = []
        try:
            for i, page in enumerate(doc):
                parts.append(f"# Page {i+1}\n\n")
                try:
                    # 先尝试提取 markdown 格式
                    md = page.get_text("markdown")
                    if not md or not md.strip():
                        # 如果 markdown 为空，回退到纯文本
                        md = page.get_text("text")
                except Exception:
                    # 如果 markdown 提取失败，使用纯文本
                    md = page.get_text("text")
                parts.append((md or "").strip())
                parts.append("\n")
        finally:
            doc.close()
        return "\n".join(parts)
    
    def process(self, input_path: Path) -> ProcessingResult:
        """处理PDF文件，返回处理结果"""
        process_start_time = time.time()
        logger.debug("PdfProcessor: Starting to process %s", input_path)
        path = Path(input_path)

        try:
            logger.debug(
                "PdfProcessor: Converting PDF to markdown with pymupdf4llm"
            )
            base_md = pymupdf4llm.to_markdown(str(path))
            text_len = len(base_md.strip())
            logger.debug(
                "PdfProcessor: Base markdown extracted, length: %s characters",
                text_len,
            )
        except Exception as e:
            logger.error(
                "PdfProcessor: Failed to convert PDF to markdown: %s: %s",
                e.__class__.__name__,
                e,
            )
            # 处理特定的 PyMuPDF textpage 错误
            if "not a textpage of this page" in str(e).lower():
                logger.warning(
                    "PdfProcessor: Encountered 'not a textpage of this page' error, using fallback extraction"
                )
                base_md = self._fallback_extract_markdown(path)
                text_len = len(base_md.strip())
                logger.debug(
                    "PdfProcessor: Fallback markdown extracted, length: %s characters",
                    text_len,
                )
            else:
                raise

        try:
            logger.debug("PdfProcessor: Opening PDF with fitz (PyMuPDF)")
            doc = fitz.open(str(path))
            logger.debug(
                "PdfProcessor: PDF opened successfully, pages: %s", len(doc)
            )

            # 存储图片信息，包括路径和位置信息
            image_info: List[Dict[str, Any]] = []

            with tempfile.TemporaryDirectory() as tmpdir:
                tmp = Path(tmpdir)
                logger.debug("PdfProcessor: Created temp directory: %s", tmp)

                # 提取所有图片并记录它们的页码和索引
                for page_index, page in enumerate(doc):
                    images = page.get_images(full=True)
                    logger.debug(
                        "PdfProcessor: Page %s/%s has %s images",
                        page_index + 1,
                        len(doc),
                        len(images),
                    )

                    for img_index, img in enumerate(images):
                        xref = img[0]
                        logger.debug(
                            "PdfProcessor: Extracting image %s/%s from page %s",
                            img_index + 1,
                            len(images),
                            page_index + 1,
                        )
                        base_image = doc.extract_image(xref)
                        ext = base_image.get("ext", "png")
                        img_bytes = base_image["image"]
                        img_path = tmp / f"p{page_index}_{img_index}.{ext}"
                        img_path.write_bytes(img_bytes)

                        # 存储图片路径和位置信息
                        image_info.append({
                            "path": img_path,
                            "page": page_index,
                            "index": img_index,
                        })
                        logger.debug("PdfProcessor: Saved image to %s", img_path)

                logger.debug("PdfProcessor: Closing PDF document")
                doc.close()
                logger.debug(
                    "PdfProcessor: Extracted %s images total", len(image_info)
                )

                # 处理图片内容
                image_descriptions: List[Tuple[Path, str, Dict[str, Any]]] = []

                if image_info:
                    # 使用OCR预处理所有图片，获取文本内容
                    ocr_results = {}
                    logger.debug("PdfProcessor: Pre-screening images with OCR")

                    # 使用更大的线程池处理OCR预处理
                    max_workers = min(32, os.cpu_count() * 4)  # 限制最大线程数，避免资源耗尽
                    logger.debug(
                        "PdfProcessor: Using thread pool with %s workers for OCR pre-screening",
                        max_workers,
                    )

                    # 线程池的某个线程里开启多个子线程，并行处理OCR预处理
                    with ThreadPoolExecutor(max_workers=max_workers) as executor:
                        futures = [
                            executor.submit(ocr_image_file, str(info["path"]))
                            for info in image_info
                        ]
                        for i, future in enumerate(as_completed(futures)):
                            try:
                                result = future.result()
                                ocr_results[i] = result
                                logger.debug(
                                    "PdfProcessor: OCR pre-screening completed for image %s/%s, text length: %s",
                                    i + 1,
                                    len(image_info),
                                    len(result),
                                )
                            except Exception as e:
                                logger.error(
                                    "PdfProcessor: OCR pre-screening failed for an image: %s: %s",
                                    e.__class__.__name__,
                                    e,
                                )
                                ocr_results[i] = ""

                    if self._use_ocr:
                        # 使用OCR处理图片
                        logger.debug("PdfProcessor: Using OCR results directly")
                        for i, result in ocr_results.items():
                            if result.strip():  # 只保留非空结果
                                image_descriptions.append(
                                    (image_info[i]["path"], result, image_info[i]))
                    else:
                        # 使用原有OCR预处理结果判断图片是否值得进一步处理
                        logger.debug(
                            "PdfProcessor: Processing images with VLM first, then Advanced OCR if enabled (advanced=%s)",
                            "ON" if self._use_advanced_ocr and self._advanced_ocr_client else "OFF",
                        )
                        # 筛选出有足够文字的图片进行处理
                        valid_images = []
                        for i, result in ocr_results.items():
                            if len(result.strip()) >= self._min_text_chars:
                                valid_images.append((i, image_info[i]["path"], result))

                        logger.debug(
                            "PdfProcessor: Found %s images with sufficient text for further processing",
                            len(valid_images),
                        )
                        
                        if valid_images:
                            # 使用批量处理器并发处理图片
                            max_workers = min(8, os.cpu_count() * 2)  # 限制并发数，避免资源耗尽
                            batch_processor = BatchProcessor(max_workers=max_workers)
                            
                            # 定义图片处理函数（返回值交由 on_success 汇总）
                            def process_image(item, idx):
                                i, img_path, ocr_result = item
                                file_size = os.path.getsize(img_path)
                                start_time = time.time()

                                # 先尝试使用VLM
                                if self._vlm_client and len(ocr_result.strip()) >= self._min_text_chars:
                                    # 检查图像尺寸
                                    skip_vlm = False
                                    try:
                                        from PIL import Image
                                        with Image.open(img_path) as img:
                                            width, height = img.size
                                            if width < 30 or height < 30:  # 设置一个安全的最小尺寸
                                                logger.info(
                                                    "PdfProcessor: Image %s is too small: %sx%s, skipping VLM processing",
                                                    i + 1,
                                                    width,
                                                    height,
                                                )
                                                skip_vlm = True  # 标记跳过 VLM 处理
                                    except ImportError:
                                        logger.warning(
                                            "PdfProcessor: PIL not installed, skipping image size check"
                                        )
                                    except Exception as e:
                                        logger.warning(
                                            "PdfProcessor: Failed to check image size: %s",
                                            e,
                                        )
                                        # 如果无法检查尺寸，我们不跳过处理

                                    # 只有当图像尺寸足够大时，才调用 VLM
                                    if not skip_vlm:
                                        try:
                                            logger.debug(
                                                "PdfProcessor: Processing image %s with VLM (OCR text length: %s)",
                                                i + 1,
                                                len(ocr_result),
                                            )
                                            description = self._describe_with_retry(img_path, i+1)
                                            if description.strip():  # 只保留非空结果
                                                elapsed = time.time() - start_time
                                                return ("vlm", description, elapsed)
                                        except Exception as e:
                                            logger.error(
                                                "PdfProcessor: VLM failed for image %s: %s",
                                                i + 1,
                                                e,
                                            )
                                    else:
                                        logger.info(
                                            "PdfProcessor: Skipped VLM for image %s due to small size",
                                            i + 1,
                                        )

                                # 若VLM失败，且开启高级OCR，则尝试高级OCR
                                if self._use_advanced_ocr and self._advanced_ocr_client:
                                    try:
                                        logger.debug(
                                            "PdfProcessor: Processing image %s with GOT-OCR2_0 (file size: %s bytes)",
                                            i + 1,
                                            file_size,
                                        )
                                        ocr_text = self._recognize_text_with_retry(img_path, i+1)
                                        if ocr_text.strip():
                                            elapsed = time.time() - start_time
                                            return ("ocr", ocr_text, elapsed)
                                    except ValueError as e:
                                        logger.warning(
                                            "PdfProcessor: GOT-OCR2_0 skipped for image %s: %s",
                                            i + 1,
                                            e,
                                        )
                                    except Exception as e:
                                        logger.error(
                                            "PdfProcessor: GOT-OCR2_0 failed for image %s: %s",
                                            i + 1,
                                            e,
                                        )

                                # 如果VLM和（可选）高级OCR都失败，使用原始OCR结果
                                if len(ocr_result.strip()) >= self._min_text_chars:
                                    logger.debug(
                                        "PdfProcessor: Using original OCR result for image %s (length: %s)",
                                        i + 1,
                                        len(ocr_result),
                                    )
                                    return ("basic_ocr", ocr_result, 0.0)
                                # 若不足阈值，不返回内容
                                return ("skip", "", 0.0)
                            
                            # 定义成功回调
                            def on_success(idx, item, result):
                                i, img_path, _ = item
                                source, text, elapsed = result
                                if source == "skip" or not text or not str(text).strip():
                                    # 跳过无内容结果
                                    return
                                if source == "vlm":
                                    logger.debug(
                                        "PdfProcessor: VLM completed for image %s, description length: %s, took %.2fs",
                                        i + 1,
                                        len(text),
                                        elapsed,
                                    )
                                elif source == "ocr":
                                    logger.debug(
                                        "PdfProcessor: GOT-OCR2_0 completed for image %s, text length: %s, took %.2fs",
                                        i + 1,
                                        len(text),
                                        elapsed,
                                    )
                                else:
                                    logger.debug(
                                        "PdfProcessor: Using original OCR result for image %s, length: %s",
                                        i + 1,
                                        len(text),
                                    )
                                image_descriptions.append((Path(img_path), text, image_info[i]))

                            # 定义错误回调
                            def on_error(idx, item, error):
                                i, img_path, ocr_result = item
                                logger.error(
                                    "PdfProcessor: Failed to process image %s: %s",
                                    i + 1,
                                    error,
                                )
                                if len(ocr_result.strip()) >= 5:  # 至少有5个字符才保留
                                    image_descriptions.append((Path(img_path), ocr_result, image_info[i]))
                            
                            # 执行批量处理
                            batch_processor.process_batch(
                                items=valid_images,
                                process_func=process_image,
                                on_success=on_success,
                                on_error=on_error
                            )

        except Exception as e:
            logger.error(
                "PdfProcessor: Error processing PDF: %s: %s",
                e.__class__.__name__,
                e,
            )
            raise

        logger.debug("PdfProcessor: Finalizing markdown content")
        markdown = base_md

        # 如果有图片描述，将它们插入到markdown中的适当位置
        if image_descriptions:
            logger.debug(
                "PdfProcessor: Adding %s image descriptions to markdown",
                len(image_descriptions),
            )
            
            # 创建一个文档结构，用于插入图片描述
            doc_structure = {}
            
            # 将图片描述按页码分组
            for i, (img_path, description, img_info) in enumerate(image_descriptions):
                page_num = img_info["page"]
                if page_num not in doc_structure:
                    doc_structure[page_num] = []
                doc_structure[page_num].append((img_info["index"], f"> **image desc**: {description}"))
            
            # 将markdown按页分割
            # 使用pymupdf4llm生成的markdown通常会包含页码标记如 "# Page 1" 或类似格式
            import re
            page_pattern = re.compile(r'(?:^|\n)#+ *(?:Page|页面|幻灯片)? *[0-9]+', re.IGNORECASE)
            page_matches = list(page_pattern.finditer(base_md))
            
            if page_matches:
                # 如果找到页码标记，按页插入图片描述
                result_parts = []
                for i, match in enumerate(page_matches):
                    start = match.start()
                    end = page_matches[i+1].start() if i+1 < len(page_matches) else len(base_md)
                    page_content = base_md[start:end]
                    
                    # 提取页码
                    page_header = page_content[:page_content.find('\n') if '\n' in page_content else len(page_content)]
                    page_num_match = re.search(r'[0-9]+', page_header)
                    if page_num_match:
                        try:
                            page_num = int(page_num_match.group()) - 1  # 转为0-based索引
                            
                            # 如果这一页有图片描述，插入到页面内容末尾
                            if page_num in doc_structure:
                                # 按图片索引排序
                                doc_structure[page_num].sort(key=lambda x: x[0])
                                image_descs = '\n\n'.join([desc for _, desc in doc_structure[page_num]])
                                page_content = page_content.rstrip() + '\n\n' + image_descs + '\n\n'
                        except ValueError:
                            pass  # 页码解析失败，跳过
                    
                    result_parts.append(page_content)
                
                markdown = ''.join(result_parts)
            else:
                # 如果没有找到页码标记，将所有图片描述添加到文档末尾
                logger.debug(
                    "PdfProcessor: No page markers found, appending all image descriptions to the end"
                )
                for i, (img_path, description, _) in enumerate(image_descriptions):
                    image_marker = f"\n\n> **image desc {i+1}**: {description}\n\n"
                    markdown += image_marker

            logger.debug(
                "PdfProcessor: Final markdown length with image descriptions: %s characters",
                len(markdown),
            )
        else:
            logger.debug(
                "PdfProcessor: No image descriptions to add, final markdown length: %s characters",
                len(markdown),
            )

        low_conf = text_len < 50
        logger.debug(
            "PdfProcessor: Confidence assessment: %s (text length: %s)",
            "LOW" if low_conf else "HIGH",
            text_len,
        )

        result = ProcessingResult(
            markdown_content=markdown,
            text_char_count=text_len,
            image_count=len(image_info) if 'image_info' in locals() else 0,
            low_confidence=low_conf,
        )
        total_elapsed = time.time() - process_start_time
        logger.debug(
            "PdfProcessor: Processing completed successfully in %.2fs",
            total_elapsed,
        )
        return result


__all__ = ["PdfProcessor"]
