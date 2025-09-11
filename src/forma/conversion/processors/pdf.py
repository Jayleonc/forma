"""Processor for PDF files."""

from __future__ import annotations

import fitz
import os
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pymupdf4llm

from ...shared.utils.retry import retry
from .batch_processor import BatchProcessor

from ...ocr import ocr_image_file, AdvancedOCRClient
from ...vision import VLMClient
from ...shared.config import get_ocr_config
from .base import ProcessingResult, Processor


class PdfProcessor(Processor):
    """PDF处理器，用于将PDF文件转换为Markdown格式"""

    def __init__(
        self,
        vlm_client: Optional[VLMClient] = None,
        use_ocr: bool = False,
        min_text_chars: int = 8,
        advanced_ocr_client: Optional[AdvancedOCRClient] = None,
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
                print(f"[DEBUG] PdfProcessor: Advanced OCR client initialized with model {config.model}")
            except Exception as e:
                print(f"[WARNING] PdfProcessor: Failed to initialize Advanced OCR client: {e}")
                self._advanced_ocr_client = None

    def _describe_with_retry(self, image_path: Path, image_index: int) -> str:
        """使用重试机制调用VLM服务描述图片"""
        
        @retry(max_tries=3, delay=1.0, backoff=2.0, 
               exceptions=(Exception,),
               on_retry=lambda e, i: print(f"[WARNING] PdfProcessor: VLM retry {i}/3 for image {image_index} due to: {e}"))
        def _describe(path, prompt):
            return self._vlm_client.describe(path, prompt_name=prompt)
        
        return _describe(image_path, "pdf_image_description")
    
    def _recognize_text_with_retry(self, image_path: Path, image_index: int) -> str:
        """使用重试机制调用高级OCR服务识别图片文字"""
        
        @retry(max_tries=3, delay=1.0, backoff=2.0, 
               exceptions=(Exception,),
               on_retry=lambda e, i: print(f"[WARNING] PdfProcessor: GOT-OCR2_0 retry {i}/3 for image {image_index} due to: {e}"))
        def _recognize(path):
            return self._advanced_ocr_client.recognize_text(path)
        
        return _recognize(image_path)
    
    def process(self, input_path: Path) -> ProcessingResult:
        """处理PDF文件，返回处理结果"""
        process_start_time = time.time()
        print(f"[DEBUG] PdfProcessor: Starting to process {input_path}")
        path = Path(input_path)

        try:
            print(
                f"[DEBUG] PdfProcessor: Converting PDF to markdown with pymupdf4llm")
            base_md = pymupdf4llm.to_markdown(str(path))
            text_len = len(base_md.strip())
            print(
                f"[DEBUG] PdfProcessor: Base markdown extracted, length: {text_len} characters")
        except Exception as e:
            print(
                f"[ERROR] PdfProcessor: Failed to convert PDF to markdown: {e.__class__.__name__}: {e}")
            raise

        try:
            print(f"[DEBUG] PdfProcessor: Opening PDF with fitz (PyMuPDF)")
            doc = fitz.open(str(path))
            print(
                f"[DEBUG] PdfProcessor: PDF opened successfully, pages: {len(doc)}")

            # 存储图片信息，包括路径和位置信息
            image_info: List[Dict[str, Any]] = []

            with tempfile.TemporaryDirectory() as tmpdir:
                tmp = Path(tmpdir)
                print(f"[DEBUG] PdfProcessor: Created temp directory: {tmp}")

                # 提取所有图片并记录它们的页码和索引
                for page_index, page in enumerate(doc):
                    images = page.get_images(full=True)
                    print(
                        f"[DEBUG] PdfProcessor: Page {page_index+1}/{len(doc)} has {len(images)} images")

                    for img_index, img in enumerate(images):
                        xref = img[0]
                        print(
                            f"[DEBUG] PdfProcessor: Extracting image {img_index+1}/{len(images)} from page {page_index+1}")
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
                        print(
                            f"[DEBUG] PdfProcessor: Saved image to {img_path}")

                print(f"[DEBUG] PdfProcessor: Closing PDF document")
                doc.close()
                print(
                    f"[DEBUG] PdfProcessor: Extracted {len(image_info)} images total")

                # 处理图片内容
                image_descriptions: List[Tuple[Path, str, Dict[str, Any]]] = []

                if image_info:
                    # 使用OCR预处理所有图片，获取文本内容
                    ocr_results = {}
                    print(f"[DEBUG] PdfProcessor: Pre-screening images with OCR")
                    
                    # 使用更大的线程池处理OCR预处理
                    max_workers = min(32, os.cpu_count() * 4)  # 限制最大线程数，避免资源耗尽
                    print(f"[DEBUG] PdfProcessor: Using thread pool with {max_workers} workers for OCR pre-screening")
                    
                    with ThreadPoolExecutor(max_workers=max_workers) as executor:
                        futures = [
                            executor.submit(ocr_image_file, str(info["path"]))
                            for info in image_info
                        ]
                        for i, future in enumerate(as_completed(futures)):
                            try:
                                result = future.result()
                                ocr_results[i] = result
                                print(
                                    f"[DEBUG] PdfProcessor: OCR pre-screening completed for image {i+1}/{len(image_info)}, text length: {len(result)}")
                            except Exception as e:
                                print(
                                    f"[ERROR] PdfProcessor: OCR pre-screening failed for an image: {e.__class__.__name__}: {e}")
                                ocr_results[i] = ""

                    if self._use_ocr:
                        # 使用OCR处理图片
                        print(f"[DEBUG] PdfProcessor: Using OCR results directly")
                        for i, result in ocr_results.items():
                            if result.strip():  # 只保留非空结果
                                image_descriptions.append(
                                    (image_info[i]["path"], result, image_info[i]))
                    else:
                        # 使用原有OCR预处理结果判断图片是否值得进一步处理
                        print(f"[DEBUG] PdfProcessor: Processing images with VLM and advanced OCR")
                        
                        # 筛选出有足够文字的图片进行处理
                        valid_images = []
                        for i, result in ocr_results.items():
                            if len(result.strip()) >= self._min_text_chars:
                                valid_images.append((i, image_info[i]["path"], result))
                        
                        print(f"[DEBUG] PdfProcessor: Found {len(valid_images)} images with sufficient text for further processing")
                        
                        if valid_images:
                            # 使用批量处理器并发处理图片
                            max_workers = min(8, os.cpu_count() * 2)  # 限制并发数，避免资源耗尽
                            batch_processor = BatchProcessor(max_workers=max_workers)
                            
                            # 定义图片处理函数
                            def process_image(item, idx):
                                i, img_path, ocr_result = item
                                file_size = os.path.getsize(img_path)
                                start_time = time.time()
                                
                                # 先尝试VLM
                                if self._vlm_client:
                                    try:
                                        description = self._describe_with_retry(img_path, i+1)
                                        if description.strip() and len(description.strip()) >= 20:
                                            elapsed = time.time() - start_time
                                            return ("vlm", description, elapsed)
                                    except Exception as e:
                                        print(f"[ERROR] PdfProcessor: VLM failed for image {i+1}: {e}")
                                
                                # 如果VLM失败，尝试高级OCR
                                if self._advanced_ocr_client:
                                    try:
                                        ocr_text = self._recognize_text_with_retry(img_path, i+1)
                                        if ocr_text.strip():
                                            elapsed = time.time() - start_time
                                            return ("ocr", ocr_text, elapsed)
                                    except Exception as e:
                                        print(f"[ERROR] PdfProcessor: GOT-OCR2_0 failed for image {i+1}: {e}")
                                
                                # 如果都失败，使用原始OCR结果
                                return ("basic_ocr", ocr_result, 0)
                            
                            # 定义成功回调
                            def on_success(idx, item, result):
                                i, img_path, _ = item
                                source, text, elapsed = result
                                if source == "vlm":
                                    print(f"[DEBUG] PdfProcessor: VLM completed for image {i+1}, description length: {len(text)}, took {elapsed:.2f}s")
                                elif source == "ocr":
                                    print(f"[DEBUG] PdfProcessor: GOT-OCR2_0 completed for image {i+1}, text length: {len(text)}, took {elapsed:.2f}s")
                                else:
                                    print(f"[DEBUG] PdfProcessor: Using original OCR result for image {i+1}, length: {len(text)}")
                                image_descriptions.append((Path(img_path), text, image_info[i]))
                            
                            # 定义错误回调
                            def on_error(idx, item, error):
                                i, img_path, ocr_result = item
                                print(f"[ERROR] PdfProcessor: Failed to process image {i+1}: {error}")
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
            print(
                f"[ERROR] PdfProcessor: Error processing PDF: {e.__class__.__name__}: {e}")
            raise

        print(f"[DEBUG] PdfProcessor: Finalizing markdown content")
        markdown = base_md

        # 如果有图片描述，将它们插入到markdown中的适当位置
        if image_descriptions:
            print(f"[DEBUG] PdfProcessor: Adding {len(image_descriptions)} image descriptions to markdown")
            
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
                print(f"[DEBUG] PdfProcessor: No page markers found, appending all image descriptions to the end")
                for i, (img_path, description, _) in enumerate(image_descriptions):
                    image_marker = f"\n\n> **image desc {i+1}**: {description}\n\n"
                    markdown += image_marker

            print(
                f"[DEBUG] PdfProcessor: Final markdown length with image descriptions: {len(markdown)} characters")
        else:
            print(
                f"[DEBUG] PdfProcessor: No image descriptions to add, final markdown length: {len(markdown)} characters")

        low_conf = text_len < 50
        print(
            f"[DEBUG] PdfProcessor: Confidence assessment: {'LOW' if low_conf else 'HIGH'} (text length: {text_len})")

        result = ProcessingResult(
            markdown_content=markdown,
            text_char_count=text_len,
            image_count=len(image_info) if 'image_info' in locals() else 0,
            low_confidence=low_conf,
        )
        total_elapsed = time.time() - process_start_time
        print(f"[DEBUG] PdfProcessor: Processing completed successfully in {total_elapsed:.2f}s")
        return result


__all__ = ["PdfProcessor"]
