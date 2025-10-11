from __future__ import annotations

import base64
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List
import logging
import mimetypes

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from ..shared.config import get_vlm_config
from ..shared.prompts import PromptManager


logger = logging.getLogger(__name__)


def _guess_mime_type(path: Path) -> str:
    """Guess the mime type of a file."""
    mime, _ = mimetypes.guess_type(path)
    return mime or "image/png"


class VLMClient(ABC):
    """Abstract base class for Vision Language Model clients."""

    @abstractmethod
    def invoke(self, image_paths: List[Path], prompt: Dict[str, Any]) -> str:
        """Invokes the VLM with a list of images and a prompt."""
        pass

    @abstractmethod
    def describe(self, image_path: Path, prompt_name: str = "default_image_description") -> str:
        """A convenience method to describe a single image."""
        pass


class OpenAIVLMClient(VLMClient):
    """VLM client using OpenAI's API via LangChain."""

    def __init__(self) -> None:
        cfg = get_vlm_config()
        self._client = ChatOpenAI(
            model=cfg.model, api_key=cfg.api_key, base_url=cfg.base_url
        )
        self._prompt_manager = PromptManager()

    def invoke(self, image_paths: List[Path], prompt: Dict[str, Any]) -> str:
        """Invokes the OpenAI API with a list of images and a complex prompt."""
        content: List[Dict[str, Any]] = [
            {"type": "text", "text": prompt.get("user", "")}]
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

        try:
            result = self._client.invoke(messages)
            return getattr(result, "content", "") or ""
        except Exception as e:
            logger.error("Error during VLM invocation: %s", e)
            return "[VLM 调用失败]"

    def describe(self, image_path: Path, prompt_name: str = "default_image_description") -> str:
        """Describes a single image using a specified prompt."""
        prompt = self._prompt_manager.get_prompt(prompt_name)
        return self.invoke([image_path], prompt)


__all__ = ["VLMClient", "OpenAIVLMClient"]
