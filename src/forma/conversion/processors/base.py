"""Base classes for document processors."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ExtractedVisualAsset:
    """Binary visual asset extracted during conversion."""

    filename: str
    content: bytes
    mime_type: str
    alt_text: str
    position_type: str = ""
    position_meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProcessingResult:
    """Result returned by processors."""

    markdown_content: str
    text_char_count: int
    image_count: int
    low_confidence: bool = False
    visual_assets: list[ExtractedVisualAsset] = field(default_factory=list)


class Processor(ABC):
    """Abstract processor for a single document type."""

    @abstractmethod
    def process(self, input_path: Path) -> ProcessingResult:  # pragma: no cover - interface
        """Process the given file and return a :class:`ProcessingResult`."""
        raise NotImplementedError

__all__ = ["ExtractedVisualAsset", "ProcessingResult", "Processor"]
