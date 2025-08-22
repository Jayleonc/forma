"""Abstraction layer for vision-language model parsing."""

from __future__ import annotations

from pathlib import Path
from typing import List
import tempfile

from .client import OpenAIVLMClient, VLMClient
from ..shared.prompts import PromptManager


class VlmParser:
    """Wrapper for VLM processing, handling file-type-specific logic."""

    def __init__(self, vlm_client: VLMClient | None = None) -> None:
        self.client = vlm_client or OpenAIVLMClient()
        self.prompt_manager = PromptManager()

    def parse(self, path: Path, prompt_name: str = "default_image_description") -> str:
        """Parse an image or PDF via the VLM service and return Markdown text."""

        prompt = self.prompt_manager.get_prompt(prompt_name)

        if path.suffix.lower() == ".pdf":
            image_paths: List[Path] = []
            import fitz

            doc = fitz.open(str(path))
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp = Path(tmpdir)
                for i, page in enumerate(doc):
                    pix = page.get_pixmap()
                    img_path = tmp / f"page_{i}.png"
                    pix.save(str(img_path))
                    image_paths.append(img_path)
                doc.close()
                return self.client.invoke(image_paths, prompt)
        else:
            return self.client.invoke([path], prompt)


__all__ = ["VlmParser"]
