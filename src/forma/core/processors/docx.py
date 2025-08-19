"""Processor for DOCX files."""

from __future__ import annotations

from pathlib import Path

import markdownify
import mammoth
from docx import Document

from .base import ProcessingResult, Processor
from ...utils.docx import docx_to_markdown_gfm


class DocxProcessor(Processor):
    """Processor for DOCX files using a hybrid approach."""

    def process(self, input_path: Path) -> ProcessingResult:
        path = str(input_path)
        md = None

        # Plan B: High-fidelity conversion with Mammoth
        # 把 Docs 转成 HTML，再转成 Markdown（保留表格结构）
        try:
            with open(path, "rb") as f:
                html = mammoth.convert_to_html(f).value

            # 转换 HTML 到 Markdown，保留表格结构
            md = markdownify.markdownify(html, heading_style="ATX").strip()
        except Exception:
            # 如果转换失败，使用 Plan A
            md = None

        # Plan A: Fallback to pure python-docx for robustness
        # 如果 Plan B 失败，使用 Plan A
        if not md:
            md = docx_to_markdown_gfm(path)

        text_len = len(md.strip())

        # Count images using python-docx (as a basic heuristic)
        # 计算图片数量
        doc = Document(path)
        image_count = 0
        for rel in doc.part._rels.values():
            if "image" in rel.target_ref:
                image_count += 1

        return ProcessingResult(
            markdown_content=md,
            text_char_count=text_len,
            image_count=image_count,
            low_confidence=text_len == 0,
        )

__all__ = ["DocxProcessor"]
