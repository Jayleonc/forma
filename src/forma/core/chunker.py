from __future__ import annotations

import re
import uuid
from typing import List, Tuple

from .models import Chunk


class MarkdownChunker:
    """Split markdown documents into hierarchical semantic chunks."""

    def __init__(self, max_length: int = 2000, source_filename: str | None = None) -> None:
        self.max_length = max_length
        self.source_filename = source_filename or ""

    def chunk(self, markdown_content: str) -> List[Chunk]:
        """Chunk markdown content using second and third level headers."""
        chunks: List[Chunk] = []

        parent_sections = self._split_sections(markdown_content, 2)
        if not parent_sections:
            chunk_id = str(uuid.uuid4())
            chunks.append(
                Chunk(
                    chunk_id=chunk_id,
                    text=markdown_content.strip(),
                    metadata={
                        "parent_id": None,
                        "source_filename": self.source_filename,
                        "header_chain": [],
                        "sibling_ids": [],
                    },
                )
            )
            return chunks

        parent_ids: List[str] = []
        for header, body in parent_sections:
            chunk_id = str(uuid.uuid4())
            text = f"## {header}\n{body}".strip()
            parent_chunk = Chunk(
                chunk_id=chunk_id,
                text=text,
                metadata={
                    "parent_id": None,
                    "source_filename": self.source_filename,
                    "header_chain": [header],
                    "sibling_ids": [],
                },
            )
            chunks.append(parent_chunk)
            parent_ids.append(chunk_id)

            if len(text) > self.max_length:
                child_sections = self._split_sections(body, 3)
                child_chunks: List[Chunk] = []
                for child_header, child_body in child_sections:
                    child_id = str(uuid.uuid4())
                    child_text = f"### {child_header}\n{child_body}".strip()
                    child_chunk = Chunk(
                        chunk_id=child_id,
                        text=child_text,
                        metadata={
                            "parent_id": chunk_id,
                            "source_filename": self.source_filename,
                            "header_chain": [header, child_header],
                            "sibling_ids": [],
                        },
                    )
                    child_chunks.append(child_chunk)
                    chunks.append(child_chunk)

                child_ids = [c.chunk_id for c in child_chunks]
                for c in child_chunks:
                    c.metadata["sibling_ids"] = [cid for cid in child_ids if cid != c.chunk_id]

        for c in chunks:
            if c.metadata.get("parent_id") is None:
                c.metadata["sibling_ids"] = [pid for pid in parent_ids if pid != c.chunk_id]

        return chunks

    def _split_sections(self, content: str, level: int) -> List[Tuple[str, str]]:
        pattern = re.compile(rf"^{'#'*level} (.+)", re.MULTILINE)
        matches = list(pattern.finditer(content))
        if not matches:
            return []
        sections: List[Tuple[str, str]] = []
        for i, match in enumerate(matches):
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            header = match.group(1).strip()
            body = content[start:end].strip()
            sections.append((header, body))
        return sections


__all__ = ["MarkdownChunker"]
