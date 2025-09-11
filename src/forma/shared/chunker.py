from __future__ import annotations

import re
import uuid
import base64
from typing import List, Tuple

from langchain.text_splitter import RecursiveCharacterTextSplitter

from .models import Chunk


class HierarchicalChunker:
    """Split markdown documents into hierarchical semantic chunks."""

    def __init__(self, max_length: int = 80000, source_filename: str | None = None) -> None:
        self.max_length = max_length
        self.source_filename = source_filename or ""
        # Track generated IDs to avoid collisions within a single run
        self._generated_ids: set[str] = set()

    def _new_id(self) -> str:
        """Generate a short, URL-safe unique ID (22 chars) based on UUID4 bytes.

        Uses base64.urlsafe_b64encode(uuid4.bytes) and strips padding '='.
        This reduces ID length from 36 (canonical UUID string) to ~22 characters.
        """
        while True:
            raw = uuid.uuid4().bytes
            sid = base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
            if sid not in self._generated_ids:
                self._generated_ids.add(sid)
                return sid

    def chunk(self, markdown_content: str) -> List[Chunk]:
        """Chunk markdown content using a hierarchical strategy."""
        # 策略1：按标准Markdown标题分块
        md_chunks = self._chunk_by_markdown_headers(markdown_content)
        if md_chunks:
            return md_chunks

        # 策略2：按语义Markdown分块
        semantic_chunks = self._chunk_by_semantic_markdown_splitter(
            markdown_content)
        if semantic_chunks:
            return semantic_chunks

        # 策略3：按常见非标准标题分块（如'一、', '1.'等）
        regex_chunks = self._chunk_by_regex_headers(markdown_content)
        if regex_chunks:
            return regex_chunks

        # 策略4：回退到递归字符分割处理未结构化文本
        return self._chunk_by_fallback_splitter(markdown_content)

    def _chunk_by_markdown_headers(self, markdown_content: str) -> List[Chunk]:
        """Attempts to chunk the document using standard Markdown headers (## to ######)."""
        start_level = -1
        for level in range(2, 7):
            pattern = re.compile(rf"^{'#'*level} (.+)", re.MULTILINE)
            if pattern.search(markdown_content):
                start_level = level
                break

        if start_level == -1:
            return []

        pattern = re.compile(rf"^{'#'*start_level} (.+)", re.MULTILINE)
        match = pattern.search(markdown_content)
        leading_text = markdown_content[: match.start()].strip(
        ) if match else ""

        chunks = self._recursive_chunk(markdown_content, start_level, None, [])

        if leading_text:
            chunk_id = self._new_id()
            chunks.insert(
                0,
                Chunk(
                    chunk_id=chunk_id, text=leading_text, metadata=self._create_metadata()
                ),
            )
        return chunks

    def _chunk_by_semantic_markdown_splitter(self, markdown_content: str) -> List[Chunk]:
        """Attempts to chunk by semantic markdown separators like bolded headers."""
        # 分隔符按从最具体到最一般的顺序排列
        # 这处理使用粗体文本作为标题的文档
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.max_length,
            chunk_overlap=int(self.max_length * 0.1),
            separators=["\n\n**", "\n\n##", "\n\n#", "\n\n", "\n", " ", ""],
        )

        texts = splitter.split_text(markdown_content)

        # 如果只生成一个块，很可能不是好的分块
        if len(texts) <= 1:
            return []

        return [
            Chunk(
                chunk_id=self._new_id(),
                text=text,
                metadata=self._create_metadata(),
            )
            for text in texts
        ]

    def _chunk_by_regex_headers(self, markdown_content: str) -> List[Chunk]:
        """Attempts to chunk by common patterns like '一、', '(一)', '1.' etc."""
        # 增强正则表达式以捕获更多非标准标题，包括中文数字
        regex_patterns = [
            r"^第[一二三四五六七八九十百千万]+章.*",  # e.g., 第一章 Title
            r"^第[一二三四五六七八九十百千万]+节.*",  # e.g., 第一节 Title
            r"^[一二三四五六七八九十百千万]+、.*",  # e.g., 一、Title
            r"^（[一二三四五六七八九十百千万]+）.*",  # e.g., （一）Title
            r"^\d+\.\s+.*",  # e.g., 1. Title
        ]
        combined_regex = "|".join(regex_patterns)
        pattern = re.compile(combined_regex, re.MULTILINE)
        matches = list(pattern.finditer(markdown_content))

        if len(matches) < 2:  # 不足两个部分，不认为是结构化的
            return []

        chunks = []
        # 添加第一个标题前的文本作为块
        first_match_start = matches[0].start()
        if first_match_start > 0:
            leading_text = markdown_content[:first_match_start].strip()
            if leading_text:
                chunks.append(Chunk(chunk_id=self._new_id(),
                              text=leading_text, metadata=self._create_metadata()))

        for i, match in enumerate(matches):
            start = match.start()
            end = matches[i + 1].start() if i + \
                1 < len(matches) else len(markdown_content)
            section_text = markdown_content[start:end].strip()

            if section_text:
                chunk_id = self._new_id()
                chunks.append(
                    Chunk(chunk_id=chunk_id, text=section_text, metadata=self._create_metadata()))

        return chunks

    def _chunk_by_fallback_splitter(self, markdown_content: str) -> List[Chunk]:
        """Fallback chunking using a basic RecursiveCharacterTextSplitter."""
        if not markdown_content.strip():
            return []

        # 这是最基本的分割器，用于未结构化文本
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.max_length,
            chunk_overlap=int(self.max_length * 0.1),  # 10% overlap
            separators=["\n\n", "\n", " ", ""],
        )

        texts = splitter.split_text(markdown_content)

        return [
            Chunk(
                chunk_id=str(uuid.uuid4()),
                text=text,
                metadata=self._create_metadata(),
            )
            for text in texts
        ]

    def _recursive_chunk(
        self,
        markdown_content: str,
        level: int,
        parent_id: str | None,
        header_chain: List[str],
    ) -> List[Chunk]:
        """递归分割Markdown内容，先按标题，再按段落分割"""
        if level > 6:
            return []

        sections = self._split_sections(markdown_content, level)
        if not sections:
            return []

        all_chunks: List[Chunk] = []
        sibling_header_chunks: List[Chunk] = []

        for header, body in sections:
            current_header_chain = header_chain + [header]
            header_chunk_id = self._new_id()

            # 递归找到所有子标题块
            sub_header_chunks = self._recursive_chunk(
                body, level + 1, header_chunk_id, current_header_chain)

            # 隔离直接属于当前标题的文本
            first_sub_header_start = -1
            for l in range(level + 1, 7):
                pattern = re.compile(rf"^{'#'*l} (.+)", re.MULTILINE)
                match = pattern.search(body)
                if match and (first_sub_header_start == -1 or match.start() < first_sub_header_start):
                    first_sub_header_start = match.start()

            text_only = body[:first_sub_header_start].strip(
            ) if first_sub_header_start != -1 else body.strip()

            # 创建当前标题的主块
            header_chunk = Chunk(
                chunk_id=header_chunk_id,
                text=f"{'#' * level} {header}",
                metadata=self._create_metadata(
                    parent_id, current_header_chain),
            )

            # 添加标题块本身。它充当容器。
            all_chunks.append(header_chunk)
            sibling_header_chunks.append(header_chunk)

            # 如果有文本，决定是分割还是合并。
            if text_only:
                if len(text_only) > self.max_length:
                    # 文本过长，应用智能段落分割。
                    paragraph_chunks = self._split_text_intelligently(
                        text_only, header_chunk_id, current_header_chain)
                    all_chunks.extend(paragraph_chunks)
                else:
                    # 文本不长，所以合并到标题块。
                    header_chunk.text += f"\n{text_only}"

            # 添加子标题块
            all_chunks.extend(sub_header_chunks)

        # 将当前级别的标题块链接为兄弟
        sibling_ids = [c.chunk_id for c in sibling_header_chunks]
        for c in sibling_header_chunks:
            c.metadata["sibling_ids"] = [
                sid for sid in sibling_ids if sid != c.chunk_id]

        return all_chunks

    def _split_text_intelligently(
        self, text: str, parent_id: str, header_chain: List[str]
    ) -> List[Chunk]:
        """按段落分割文本，将它们分组到不超过max_length的块中。"""
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

        all_sub_chunks: List[Chunk] = []
        current_chunk_paragraphs: List[str] = []
        current_chunk_size = 0

        for para in paragraphs:
            para_len = len(para)
            # 检查添加下一段是否会超过限制。
            # 如果当前块为空，我们必须添加段落，不管它的大小如何。
            if not current_chunk_paragraphs or (current_chunk_size + para_len + 2) <= self.max_length:
                current_chunk_paragraphs.append(para)
                current_chunk_size += para_len + 2  # +2 for newline characters
            else:
                # 封印当前块。
                chunk_text = "\n\n".join(current_chunk_paragraphs)
                sub_chunk = Chunk(
                    chunk_id=self._new_id(),
                    text=chunk_text,
                    metadata=self._create_metadata(parent_id, header_chain),
                )
                all_sub_chunks.append(sub_chunk)

                # 开始一个新块，当前段落。
                current_chunk_paragraphs = [para]
                current_chunk_size = para_len

        # 封印最后一个块。
        if current_chunk_paragraphs:
            chunk_text = "\n\n".join(current_chunk_paragraphs)
            sub_chunk = Chunk(
                chunk_id=self._new_id(),
                text=chunk_text,
                metadata=self._create_metadata(parent_id, header_chain),
            )
            all_sub_chunks.append(sub_chunk)

        # 将创建的子块链接为兄弟。
        sibling_ids = [c.chunk_id for c in all_sub_chunks]
        for c in all_sub_chunks:
            c.metadata["sibling_ids"] = [
                sid for sid in sibling_ids if sid != c.chunk_id]

        return all_sub_chunks

    def _create_metadata(
        self, parent_id: str | None = None, header_chain: List[str] | None = None
    ) -> dict:
        return {
            "parent_id": parent_id,
            "source_filename": self.source_filename,
            "header_chain": header_chain or [],
            "sibling_ids": [],
        }

    def _split_sections(self, content: str, level: int) -> List[Tuple[str, str]]:
        pattern = re.compile(rf"^{'#'*level} (.+)", re.MULTILINE)
        matches = list(pattern.finditer(content))
        if not matches:
            return []
        sections: List[Tuple[str, str]] = []
        for i, match in enumerate(matches):
            start = match.end()
            end = matches[i + 1].start() if i + \
                1 < len(matches) else len(content)
            header = match.group(1).strip()
            body = content[start:end].strip()
            sections.append((header, body))
        return sections


__all__ = ["HierarchicalChunker"]
