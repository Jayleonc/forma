"""Prompt management for VLM prompts loaded from YAML."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Any

import yaml


class PromptManager:
    """Singleton manager that loads prompts from a YAML file."""

    _instance: "PromptManager | None" = None

    def __new__(cls) -> "PromptManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_prompts()
        return cls._instance

    def _load_prompts(self) -> None:
        root = Path(__file__).resolve().parent.parent.parent
        path = root / "prompts.yaml"
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        prompts = data.get("prompts") or {}
        if not isinstance(prompts, dict):
            raise ValueError("Invalid prompts configuration")
        self._prompts: Dict[str, Dict[str, Any]] = prompts

    def get_prompt(self, name: str) -> Dict[str, Any]:
        """Return the prompt dictionary for the given name."""
        try:
            return self._prompts[name]
        except KeyError as exc:
            raise KeyError(f"Prompt '{name}' not found") from exc


__all__ = ["PromptManager"]
