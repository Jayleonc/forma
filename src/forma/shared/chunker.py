from __future__ import annotations

import re
import uuid
from typing import List, Tuple

from langchain.text_splitter import RecursiveCharacterTextSplitter

from .models import Chunk


class HierarchicalChunker:
    """Split markdown documents into hierarchical semantic chunks."""

    def __init__(self, max_length: int = 80000, source_filename: str | None = None) -> None:
        self.max_length = max_length
        self.source_filename = source_filename or ""

    def chunk(self, markdown_content: str) -> List[Chunk]:
        """Chunk markdown content using a hierarchical strategy."""
        # Strategy 1: Chunk by standard Markdown headers
        md_chunks = self._chunk_by_markdown_headers(markdown_content)
        if md_chunks:
            return md_chunks

        # Strategy 2: Chunk by semantic markdown splitting (handles bold headers etc.)
        semantic_chunks = self._chunk_by_semantic_markdown_splitter(
            markdown_content)
        if semantic_chunks:
            return semantic_chunks

        # Strategy 3: Chunk by common non-standard headers (e.g., '一、', '1.')
        regex_chunks = self._chunk_by_regex_headers(markdown_content)
        if regex_chunks:
            return regex_chunks

        # Strategy 4: Fallback to recursive character splitting for unstructured text
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
            chunk_id = str(uuid.uuid4())
            chunks.insert(
                0,
                Chunk(
                    chunk_id=chunk_id, text=leading_text, metadata=self._create_metadata()
                ),
            )
        return chunks

    def _chunk_by_semantic_markdown_splitter(self, markdown_content: str) -> List[Chunk]:
        """Attempts to chunk by semantic markdown separators like bolded headers."""
        # Separators are ordered from most specific to most general.
        # This handles documents that use bold text for headers.
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.max_length,
            chunk_overlap=int(self.max_length * 0.1),
            separators=["\n\n**", "\n\n##", "\n\n#", "\n\n", "\n", " ", ""],
        )

        texts = splitter.split_text(markdown_content)

        # If it only results in one chunk, it's likely not a good split.
        if len(texts) <= 1:
            return []

        return [
            Chunk(
                chunk_id=str(uuid.uuid4()),
                text=text,
                metadata=self._create_metadata(),
            )
            for text in texts
        ]

    def _chunk_by_regex_headers(self, markdown_content: str) -> List[Chunk]:
        """Attempts to chunk by common patterns like '一、', '(一)', '1.' etc."""
        # Enhanced regex to capture more non-standard headers, including Chinese numerals
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

        if len(matches) < 2:  # Not enough sections to be considered structured
            return []

        chunks = []
        # Add the text before the first header as a chunk
        first_match_start = matches[0].start()
        if first_match_start > 0:
            leading_text = markdown_content[:first_match_start].strip()
            if leading_text:
                chunks.append(Chunk(chunk_id=str(uuid.uuid4()),
                              text=leading_text, metadata=self._create_metadata()))

        for i, match in enumerate(matches):
            start = match.start()
            end = matches[i + 1].start() if i + \
                1 < len(matches) else len(markdown_content)
            section_text = markdown_content[start:end].strip()

            if section_text:
                chunk_id = str(uuid.uuid4())
                chunks.append(
                    Chunk(chunk_id=chunk_id, text=section_text, metadata=self._create_metadata()))

        return chunks

    def _chunk_by_fallback_splitter(self, markdown_content: str) -> List[Chunk]:
        """Fallback chunking using a basic RecursiveCharacterTextSplitter."""
        if not markdown_content.strip():
            return []

        # This is the most basic splitter for unstructured text.
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
        """Helper to recursively split markdown content by header and then by paragraph if needed."""
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

            # Recursively find all chunks from sub-headers (level+1 and deeper)
            sub_header_chunks = self._recursive_chunk(
                body, level + 1, header_chunk_id, current_header_chain)

            # Isolate the text that belongs directly to the current header
            first_sub_header_start = -1
            for l in range(level + 1, 7):
                pattern = re.compile(rf"^{'#'*l} (.+)", re.MULTILINE)
                match = pattern.search(body)
                if match and (first_sub_header_start == -1 or match.start() < first_sub_header_start):
                    first_sub_header_start = match.start()

            text_only = body[:first_sub_header_start].strip(
            ) if first_sub_header_start != -1 else body.strip()

            # Create the main chunk for the current header
            header_chunk = Chunk(
                chunk_id=header_chunk_id,
                text=f"{'#' * level} {header}",
                metadata=self._create_metadata(
                    parent_id, current_header_chain),
            )

            # Add the header chunk itself. It acts as a container.
            all_chunks.append(header_chunk)
            sibling_header_chunks.append(header_chunk)

            # If there's text, decide whether to split it or merge it.
            if text_only:
                if len(text_only) > self.max_length:
                    # Text is too long, apply intelligent paragraph splitting.
                    paragraph_chunks = self._split_text_intelligently(
                        text_only, header_chunk_id, current_header_chain)
                    all_chunks.extend(paragraph_chunks)
                else:
                    # Text is not too long, so merge it into the header chunk.
                    header_chunk.text += f"\n{text_only}"

            # Add chunks from sub-headers
            all_chunks.extend(sub_header_chunks)

        # Link header chunks at the current level as siblings
        sibling_ids = [c.chunk_id for c in sibling_header_chunks]
        for c in sibling_header_chunks:
            c.metadata["sibling_ids"] = [
                sid for sid in sibling_ids if sid != c.chunk_id]

        return all_chunks

    def _split_text_intelligently(
        self, text: str, parent_id: str, header_chain: List[str]
    ) -> List[Chunk]:
        """Splits a block of text by paragraphs, grouping them into chunks under max_length."""
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

        all_sub_chunks: List[Chunk] = []
        current_chunk_paragraphs: List[str] = []
        current_chunk_size = 0

        for para in paragraphs:
            para_len = len(para)
            # Check if adding the next paragraph would exceed the limit.
            # If the current chunk is empty, we must add the paragraph regardless of its size.
            if not current_chunk_paragraphs or (current_chunk_size + para_len + 2) <= self.max_length:
                current_chunk_paragraphs.append(para)
                current_chunk_size += para_len + 2  # +2 for newline characters
            else:
                # Seal the current chunk.
                chunk_text = "\n\n".join(current_chunk_paragraphs)
                sub_chunk = Chunk(
                    chunk_id=str(uuid.uuid4()),
                    text=chunk_text,
                    metadata=self._create_metadata(parent_id, header_chain),
                )
                all_sub_chunks.append(sub_chunk)

                # Start a new chunk with the current paragraph.
                current_chunk_paragraphs = [para]
                current_chunk_size = para_len

        # Seal the last chunk.
        if current_chunk_paragraphs:
            chunk_text = "\n\n".join(current_chunk_paragraphs)
            sub_chunk = Chunk(
                chunk_id=str(uuid.uuid4()),
                text=chunk_text,
                metadata=self._create_metadata(parent_id, header_chain),
            )
            all_sub_chunks.append(sub_chunk)

        # Link the created sub-chunks as siblings.
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
