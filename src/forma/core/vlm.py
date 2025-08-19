"""Abstraction layer for vision-language model parsing."""

from __future__ import annotations

from pathlib import Path
from typing import List, Dict, Any
import base64
import tempfile

import mimetypes

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from ..config import get_vlm_config
from .prompt_manager import PromptManager


def _guess_mime_type(path: Path) -> str:
    """Guess the mime type of a file."""
    mime, _ = mimetypes.guess_type(path)
    return mime or "image/png"


class VlmParser:
    """Wrapper around a VLM service for deep document understanding."""

    def __init__(self) -> None:
        cfg = get_vlm_config()
        self.client = ChatOpenAI(
            model=cfg.model, api_key=cfg.api_key, base_url=cfg.base_url
        )
        self.prompt_manager = PromptManager()
    def _call_api(self, image_paths: List[Path], prompt: Dict[str, Any]) -> str:
        content = [{"type": "text", "text": prompt.get("user", "")}]
        for path in image_paths:
            b64_string = base64.b64encode(path.read_bytes()).decode("utf-8")
            mime_type = _guess_mime_type(path)
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{b64_string}"},
                }
            )

        messages = []
        system_prompt = prompt.get("system")
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=content))

        result = self.client.invoke(messages)
        return getattr(result, "content", "") or ""

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
                return self._call_api(image_paths, prompt)
        else:
            return self._call_api([path], prompt)


__all__ = ["VlmParser"]
