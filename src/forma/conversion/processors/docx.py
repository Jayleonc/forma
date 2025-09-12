"""Processor for DOCX files."""

from __future__ import annotations

import os
import time
from pathlib import Path
import tempfile
from typing import Any, Optional

from docx import Document
from docx.document import Document as DocumentObject
from docx.table import _Cell, Table
from docx.text.paragraph import Paragraph
from docx.oxml.text.paragraph import CT_P
from docx.oxml.table import CT_Tbl

from ...shared.utils.retry import retry

from ...ocr import ocr_image_file, AdvancedOCRClient
from ...vision import VLMClient
from ...shared.config import get_ocr_config
from .base import ProcessingResult, Processor


class DocxProcessor(Processor):
    """Processor for DOCX files."""

    def __init__(self, vlm_client: Optional[VLMClient] = None, advanced_ocr_client: Optional[AdvancedOCRClient] = None, use_advanced_ocr: bool = False) -> None:
        """
        Initialize the DOCX processor.

        Args:
            vlm_client: Optional VLM client for image description
            advanced_ocr_client: Optional advanced OCR client for text recognition
        """
        self._vlm_client = vlm_client
        self._min_text_chars = 8  # 最小文本字符数阈值，用于预处理
        self._use_advanced_ocr = use_advanced_ocr

        # 仅在开启开关时才尝试创建高级OCR客户端
        self._advanced_ocr_client = None
        if self._use_advanced_ocr:
            self._advanced_ocr_client = advanced_ocr_client
            if self._advanced_ocr_client is None:
                try:
                    config = get_advanced_ocr_config()
                    self._advanced_ocr_client = AdvancedOCRClient(
                        api_key=config.api_key,
                        model=config.model,
                        base_url=config.base_url,
                        max_file_size=config.max_file_size
                    )
                    print(f"[DEBUG] DocxProcessor: Advanced OCR client initialized with model {config.model}")
                except Exception as e:
                    print(f"[WARNING] DocxProcessor: Failed to initialize Advanced OCR client: {e}")
                    self._advanced_ocr_client = None

    def _describe_with_retry(self, image_path: Path, image_id: str = None) -> str:
        """使用重试机制调用VLM服务描述图片"""
        
        @retry(max_tries=3, delay=1.0, backoff=2.0, 
               exceptions=(Exception,),
               on_retry=lambda e, i: print(f"[WARNING] DocxProcessor: VLM retry {i}/3 for image {image_id or 'unknown'} due to: {e}"))
        def _describe(path, prompt):
            return self._vlm_client.describe(path, prompt_name=prompt)
        
        return _describe(image_path, "docx_image_description")
    
    def _recognize_text_with_retry(self, image_path: Path, image_id: str = None) -> str:
        """使用重试机制调用高级OCR服务识别图片文字"""
        
        @retry(max_tries=3, delay=1.0, backoff=2.0, 
               exceptions=(Exception,),
               on_retry=lambda e, i: print(f"[WARNING] DocxProcessor: GOT-OCR2_0 retry {i}/3 for image {image_id or 'unknown'} due to: {e}"))
        def _recognize(path):
            return self._advanced_ocr_client.recognize_text(path)
        
        return _recognize(image_path)
    
    def process(self, input_path: Path) -> ProcessingResult:
        """处理DOCX文件，返回处理结果"""
        process_start_time = time.time()
        doc = Document(input_path)
        markdown_parts = []
        image_count = 0

        # Process blocks (paragraphs and tables) in order
        for block in self._iter_block_items(doc):
            if isinstance(block, Paragraph):
                # Process images within the paragraph
                if self._vlm_client and "graphicData" in block._p.xml:
                    for r_id in self._get_image_rids(block):
                        try:
                            image_part = doc.part.rels[r_id].target_part
                            image_bytes = image_part.blob
                            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temp_file:
                                temp_file.write(image_bytes)
                                temp_image_path = Path(temp_file.name)

                            # 先使用原有OCR进行预处理，判断图片是否值得进一步处理
                            try:
                                # 使用原有OCR进行预处理
                                ocr_result = ocr_image_file(
                                    str(temp_image_path))
                                print(
                                    f"[DEBUG] DocxProcessor: OCR pre-screening completed, text length: {len(ocr_result)}")

                                # 获取文件大小
                                file_size = os.path.getsize(temp_image_path)
                                description = ""

                                # 仅处理原有OCR预处理识别出有足够文字的图片
                                if len(ocr_result.strip()) >= self._min_text_chars:
                                    # 1) 先尝试 VLM
                                    if self._vlm_client:
                                        try:
                                            print(f"[DEBUG] DocxProcessor: Processing image with VLM")
                                            vlm_description = self._vlm_client.describe(temp_image_path, prompt_name="docx_image_description")
                                            if vlm_description.strip():
                                                description = vlm_description
                                                print(f"[DEBUG] DocxProcessor: VLM completed, description length: {len(vlm_description)}")
                                        except Exception as e:
                                            print(f"[ERROR] DocxProcessor: VLM failed: {e}")

                                    # 2) 若VLM失败或为空，且开启高级OCR则尝试高级OCR
                                    if not description and self._use_advanced_ocr and self._advanced_ocr_client:
                                        try:
                                            print(f"[DEBUG] DocxProcessor: Processing image with GOT-OCR2_0 (file size: {file_size} bytes)")
                                            ocr_text = self._advanced_ocr_client.recognize_text(temp_image_path)
                                            if ocr_text.strip():  # 只保留非空结果
                                                description = ocr_text
                                                print(f"[DEBUG] DocxProcessor: GOT-OCR2_0 completed, text length: {len(ocr_text)}")
                                        except ValueError as e:
                                            # 文件大小超限或其他值错误
                                            print(f"[WARNING] DocxProcessor: GOT-OCR2_0 skipped: {e}")
                                        except Exception as e:
                                            # 其他错误
                                            print(f"[ERROR] DocxProcessor: GOT-OCR2_0 failed: {e}")

                                    # 3) 若高级OCR和VLM都失败，使用原有OCR结果
                                    if not description and ocr_result.strip():
                                        description = ocr_result
                                        print(f"[DEBUG] DocxProcessor: Using original OCR result, length: {len(ocr_result)}")
                                else:
                                    print(f"[DEBUG] DocxProcessor: Skipping image (insufficient text: {len(ocr_result.strip())} chars)")
                            except Exception as e:
                                print(f"[ERROR] DocxProcessor: OCR pre-screening failed: {e}")
                                # 如果预处理失败，尝试直接使用VLM
                                if self._vlm_client:
                                    try:
                                        start_time = time.time()
                                        vlm_description = self._describe_with_retry(temp_image_path)
                                        # 检查VLM结果质量，如果结果过短，则不使用
                                        if vlm_description.strip() and len(vlm_description.strip()) >= 20:  # 至少20个字符才认为有效
                                            description = vlm_description
                                            elapsed = time.time() - start_time
                                            print(f"[DEBUG] DocxProcessor: VLM fallback completed, description length: {len(vlm_description)}, took {elapsed:.2f}s")
                                        else:
                                            print(
                                                f"[WARNING] DocxProcessor: VLM result too short in fallback path, length: {len(vlm_description.strip() if vlm_description else '')}")
                                            # 不设置description，这样后面会显示“无法识别图片内容”
                                    except Exception as e:
                                        print(f"[ERROR] DocxProcessor: VLM fallback failed: {e}")

                            if description:
                                markdown_parts.append(
                                    f"\n\n> **image desc**: {description}\n\n")
                                image_count += 1
                            else:
                                print(
                                    f"[WARNING] DocxProcessor: No content extracted for image")
                                markdown_parts.append("\n\n> [无法识别图片内容]\n\n")

                            # 清理临时文件
                            temp_image_path.unlink()
                        except Exception as e:
                            print(
                                f"[ERROR] DocxProcessor: Error processing image {r_id}: {e}")
                            markdown_parts.append("\n\n> [图片处理失败]\n\n")

                # Process text
                text = block.text.strip()
                if text:
                    markdown_parts.append(text)

            elif isinstance(block, Table):
                md_table = self._table_to_markdown(block)
                if md_table:
                    markdown_parts.append(md_table)

        md = "\n\n".join(markdown_parts).strip()
        text_len = len(md)

        total_elapsed = time.time() - process_start_time
        print(f"[DEBUG] DocxProcessor: Processing completed in {total_elapsed:.2f}s")
        
        return ProcessingResult(
            markdown_content=md,
            text_char_count=text_len,
            image_count=image_count,
            low_confidence=text_len == 0,
        )

    def _get_image_rids(self, p: Paragraph) -> list[str]:
        """获取段落中的所有图片关系ID"""
        return p._p.xpath('.//a:blip/@r:embed')

    def _iter_block_items(self, parent):
        """遍历文档中的所有段落和表格"""

        if isinstance(parent, DocumentObject):
            parent_elm = parent.element.body
        elif isinstance(parent, _Cell):
            parent_elm = parent._tc
        else:
            raise ValueError("Unsupported parent type")

        for child in parent_elm.iterchildren():
            if isinstance(child, CT_P):
                yield Paragraph(child, parent)
            elif isinstance(child, CT_Tbl):
                yield Table(child, parent)

    def _escape_pipes(self, text: str) -> str:
        """Escapes pipe characters in text for Markdown tables."""
        return text.replace("|", r"\|").replace("\n", "<br>")

    def _table_to_markdown(self, table: Table) -> str:
        """将 docx 表格转换为 GFM Markdown 表格"""

        rows_cells = []
        for row in table.rows:
            unique_cells = set()
            row_texts = []
            for cell in row.cells:
                if cell._tc not in unique_cells:
                    row_texts.append(self._escape_pipes(cell.text.strip()))
                    unique_cells.add(cell._tc)

            while row_texts and not row_texts[-1].strip():
                row_texts.pop()
            rows_cells.append(row_texts or [""])

        if not rows_cells:
            return ""

        max_cols = max(len(r) for r in rows_cells)
        full_rows = [r + [""] * (max_cols - len(r)) for r in rows_cells]

        header = full_rows[0]
        separator = ["---"] * max_cols
        body = full_rows[1:] if len(full_rows) > 1 else []

        lines = [
            "| " + " | ".join(header) + " |",
            "| " + " | ".join(separator) + " |",
        ]
        for r in body:
            lines.append("| " + " | ".join(r) + " |")

        has_merged_cells = any(
            len(set(c._tc for c in r.cells)) != len(r.cells) for r in table.rows)
        if has_merged_cells:
            lines.insert(0, "> _此表包含合并单元格，Markdown 展示可能有信息丢失，请参考原文。_\n")

        return "\n".join(lines)


__all__ = ["DocxProcessor"]
