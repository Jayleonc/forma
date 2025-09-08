"""Processor for DOCX files."""

from __future__ import annotations

from pathlib import Path
import tempfile
from typing import Any

from docx import Document
from docx.document import Document as DocumentObject
from docx.table import _Cell, Table
from docx.text.paragraph import Paragraph
from docx.oxml.text.paragraph import CT_P
from docx.oxml.table import CT_Tbl

from ...vision import VLMClient
from .base import ProcessingResult, Processor


class DocxProcessor(Processor):
    """Processor for DOCX files."""

    def __init__(self, vlm_client: VLMClient | None = None) -> None:
        self._vlm_client = vlm_client

    def process(self, input_path: Path) -> ProcessingResult:
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
                            
                            description = self._vlm_client.describe(temp_image_path, prompt_name="docx_image_description")
                            markdown_parts.append(f"\n\n> 图片描述: {description}\n\n")
                            image_count += 1
                            temp_image_path.unlink()
                        except Exception as e:
                            print(f"Error processing image {r_id}: {e}")
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
        
        has_merged_cells = any(len(set(c._tc for c in r.cells)) != len(r.cells) for r in table.rows)
        if has_merged_cells:
            lines.insert(0, "> _此表包含合并单元格，Markdown 展示可能有信息丢失，请参考原文。_\n")

        return "\n".join(lines)


__all__ = ["DocxProcessor"]
