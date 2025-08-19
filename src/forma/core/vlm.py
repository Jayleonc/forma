"""Abstraction layer for vision-language model parsing."""

from __future__ import annotations

from pathlib import Path
from typing import List
import base64
import tempfile

from openai import OpenAI

from ..config import get_vlm_config


class VlmParser:
    """Wrapper around a VLM service for deep document understanding."""

    def __init__(self) -> None:
        cfg = get_vlm_config()
        self.client = OpenAI(api_key=cfg.api_key, base_url=cfg.base_url)
        self.model = cfg.model or "gpt-4o-mini"

    def _encode_image(self, path: Path) -> str:
        return base64.b64encode(path.read_bytes()).decode("utf-8")

    def _call_api(self, images: List[str], prompt: str) -> str:
        content = [{"type": "text", "text": prompt}]
        for img in images:
            content.append({"type": "input_image", "image_base64": img})

        resp = self.client.responses.create(
            model=self.model,
            input=[{"role": "user", "content": content}],
        )
        try:  # Extract text field from response
            return resp.output[0].content[0].text  # type: ignore[index]
        except Exception:
            return ""

    def parse(self, path: Path, prompt: str) -> str:
        """Parse an image or PDF via the VLM service and return Markdown text."""

        if path.suffix.lower() == ".pdf":
            images: List[str] = []
            import fitz  # type: ignore

            doc = fitz.open(str(path))
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp = Path(tmpdir)
                for i, page in enumerate(doc):
                    pix = page.get_pixmap()
                    img_path = tmp / f"page_{i}.png"
                    pix.save(str(img_path))
                    images.append(self._encode_image(img_path))
            doc.close()
            return self._call_api(images, prompt)
        else:
            img = self._encode_image(path)
            return self._call_api([img], prompt)


__all__ = ["VlmParser"]
