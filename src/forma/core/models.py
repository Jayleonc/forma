from __future__ import annotations

from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field


class Chunk(BaseModel):
    """Represents a chunk of text extracted from a markdown document."""

    chunk_id: str
    text: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DistilledKnowledge(BaseModel):
    """Knowledge distilled from a chunk of text."""

    summary: str
    qa_pairs: List[Dict[str, str]] = Field(default_factory=list)
    hypothetical_questions: List[str] = Field(default_factory=list)
    entities: Dict[str, List[str]] = Field(default_factory=dict)


class EnrichedChunk(Chunk):
    """A chunk that has been enriched with distilled knowledge."""

    knowledge: DistilledKnowledge


class AuthoritativeKnowledgeUnit(BaseModel):
    """Represents an authoritative unit of knowledge synthesised across chunks."""

    theme: str
    canonical_question: str
    canonical_answer: str
    source_chunks: List[str] = Field(default_factory=list)
    raw_knowledge_snippets: Optional[List[Dict[str, Any]]] = None


__all__ = [
    "Chunk",
    "DistilledKnowledge",
    "EnrichedChunk",
    "AuthoritativeKnowledgeUnit",
]
