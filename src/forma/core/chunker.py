from __future__ import annotations

import re
import uuid
from typing import List, Tuple

from .models import Chunk


class MarkdownChunker:
    """Split markdown documents into hierarchical semantic chunks."""

    def __init__(self, max_length: int = 80000, source_filename: str | None = None) -> None:
        self.max_length = max_length
        self.source_filename = source_filename or ""

    def chunk(self, markdown_content: str) -> List[Chunk]:
        """Recursively chunk markdown content using headers up to level 6."""
        chunks = self._recursive_chunk(markdown_content, 2, None, [])

        # Find content before the first level 2 header
        pattern = re.compile(r"^## (.+)", re.MULTILINE)
        match = pattern.search(markdown_content)

        leading_text = markdown_content[:match.start()].strip(
        ) if match else markdown_content.strip()

        if not chunks:
            # If no sections were found, the whole document is one chunk
            if leading_text:
                chunk_id = str(uuid.uuid4())
                return [Chunk(chunk_id=chunk_id, text=leading_text, metadata=self._create_metadata())]
            return []

        if leading_text:
            # If there is text before the first header, create a chunk for it
            chunk_id = str(uuid.uuid4())
            chunks.insert(0, Chunk(chunk_id=chunk_id,
                          text=leading_text, metadata=self._create_metadata()))

        return chunks

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


__all__ = ["MarkdownChunker"]
