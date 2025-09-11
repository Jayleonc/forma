"""Enhanced chunker with bold header recognition for hierarchical semantic chunks."""

from __future__ import annotations

import re
import uuid
from typing import List, Tuple

from .chunker import HierarchicalChunker
from .models import Chunk


class HierarchicalChunkerV2(HierarchicalChunker):
    """Enhanced chunker that recognizes bold headers as semantic sub-headers.
    
    This chunker extends the standard HierarchicalChunker by adding the ability to
    recognize bold text lines (like "**功能：**") as semantic sub-headers under their
    parent Markdown headers. This is particularly useful for documents that use bold
    text as section headers rather than standard Markdown headers (###).
    """

    def _recursive_chunk(
        self,
        markdown_content: str,
        level: int,
        parent_id: str | None,
        header_chain: List[str],
    ) -> List[Chunk]:
        """递归分割Markdown内容，先按标题，再按段落分割，增强识别加粗行作为子标题"""
        if level > 6:
            return []

        sections = self._split_sections(markdown_content, level)
        if not sections:
            return []

        all_chunks: List[Chunk] = []
        sibling_header_chunks: List[Chunk] = []

        for header, body in sections:
            current_header_chain = header_chain + [header]
            header_chunk_id = str(uuid.uuid4())

            # 递归找到所有子标题块
            sub_header_chunks = super()._recursive_chunk(
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
            
            # 如果没有找到标准子标题，但有加粗行作为语义子标题，则处理这些加粗行
            if not sub_header_chunks and text_only:
                bold_header_chunks = self._extract_bold_headers_as_chunks(
                    text_only, header_chunk_id, current_header_chain)
                if bold_header_chunks:
                    all_chunks.extend(bold_header_chunks)
                    # 如果找到了加粗行子标题，从主标题块中移除文本，避免重复
                    header_chunk.text = f"{'#' * level} {header}"

            # 添加子标题块
            all_chunks.extend(sub_header_chunks)

        # 将当前级别的标题块链接为兄弟
        sibling_ids = [c.chunk_id for c in sibling_header_chunks]
        for c in sibling_header_chunks:
            c.metadata["sibling_ids"] = [
                sid for sid in sibling_ids if sid != c.chunk_id]

        return all_chunks

    def _extract_bold_headers_as_chunks(
        self, text: str, parent_id: str, header_chain: List[str]
    ) -> List[Chunk]:
        """Extracts sections based on bold headers and creates chunks.

        This method identifies lines starting with '**' as semantic sub-headers
        and creates a chunk for each, including the header and its subsequent content.
        This implementation is designed to be robust against incorrect splitting of words.
        """
        lines = text.split('\n')
        chunks = []
        current_chunk_lines = []
        current_header = None

        for line in lines:
            strip_line = line.strip()
            if strip_line.startswith('**') and strip_line.endswith('**'):
                # When a new bold header is found, save the previous chunk
                if current_chunk_lines:
                    chunk_text = '\n'.join(current_chunk_lines).strip()
                    if chunk_text:
                        clean_header = re.sub(r'[\:：\*]*\s*$', '', current_header or "").strip()
                        current_header_chain = header_chain + [clean_header]
                        chunk_id = str(uuid.uuid4())
                        metadata = self._create_metadata(parent_id, current_header_chain)
                        chunks.append(Chunk(chunk_id=chunk_id, text=chunk_text, metadata=metadata))
                
                # Start a new chunk
                current_chunk_lines = [line]
                current_header = strip_line
            else:
                # Append content to the current chunk
                current_chunk_lines.append(line)

        # Save the last chunk
        if current_chunk_lines:
            chunk_text = '\n'.join(current_chunk_lines).strip()
            if chunk_text:
                clean_header = re.sub(r'[\:：\*]*\s*$', '', current_header or "").strip()
                current_header_chain = header_chain + [clean_header]
                chunk_id = str(uuid.uuid4())
                metadata = self._create_metadata(parent_id, current_header_chain)
                chunks.append(Chunk(chunk_id=chunk_id, text=chunk_text, metadata=metadata))

        # Set sibling relationships for the newly created chunks.
        sibling_ids = [c.chunk_id for c in chunks]
        for c in chunks:
            c.metadata["sibling_ids"] = [sid for sid in sibling_ids if sid != c.chunk_id]

        return chunks


__all__ = ["HierarchicalChunkerV2"]
