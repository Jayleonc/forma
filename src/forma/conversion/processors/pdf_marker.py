"""Processor for PDF files using Marker."""

from __future__ import annotations

from pathlib import Path

import marker

from .base import ProcessingResult, Processor


class PdfMarkerProcessor(Processor):
    """Processor for PDF files using the marker-pdf library."""

    def __init__(self, use_llm: bool = True):
        """Initialize the processor.

        Args:
            use_llm: Whether to use an LLM for post-processing.
        """
        self.use_llm = use_llm

    def process(self, input_path: Path) -> ProcessingResult:
        """Process the PDF file using marker.

        Args:
            input_path: The path to the input PDF file.

        Returns:
            The processing result.
        """
        # TODO: Add error handling for marker execution
        markdown_content, metadata = marker.convert_single_pdf(
            str(input_path), use_llm=self.use_llm
        )

        text_len = len(markdown_content.strip())
        # Marker doesn't directly give us image count, so we'll set it to 0
        # We can potentially parse the markdown to count image tags if needed
        image_count = markdown_content.count("![")

        # Confidence is not directly provided by marker, we can use text length as a proxy
        low_conf = text_len < 50

        return ProcessingResult(
            markdown_content=markdown_content,
            text_char_count=text_len,
            image_count=image_count,
            low_confidence=low_conf,
        )


__all__ = ["PdfMarkerProcessor"]
