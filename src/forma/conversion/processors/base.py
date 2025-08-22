"""Base classes for document processors."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ProcessingResult:
    """Result returned by processors."""

    markdown_content: str
    text_char_count: int
    image_count: int
    low_confidence: bool = False


class Processor(ABC):
    """Abstract processor for a single document type."""

    @abstractmethod
    def process(self, input_path: Path) -> ProcessingResult:  # pragma: no cover - interface
        """Process the given file and return a :class:`ProcessingResult`."""
        raise NotImplementedError

__all__ = ["ProcessingResult", "Processor"]
