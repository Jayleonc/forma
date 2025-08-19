"""Prompt management for VLM prompts loaded from YAML."""

from __future__ import annotations

from pathlib import Path
from threading import Lock
from typing import Any, Dict

import yaml


class PromptManager:
    """Thread-safe singleton manager for loading prompts from a YAML file."""

    _instance: "PromptManager | None" = None
    _lock = Lock()

    def __new__(cls) -> "PromptManager":
        if cls._instance is None:
            with cls._lock:
                # Double-check locking to prevent race conditions
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._load_prompts()
        return cls._instance

    def _load_prompts(self) -> None:
        """Load prompts from the YAML file."""
        try:
            root = Path(__file__).resolve().parent.parent.parent.parent
            path = root / "prompts.yaml"
            with path.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            prompts = data.get("prompts") or {}
            if not isinstance(prompts, dict):
                raise ValueError("Invalid 'prompts' structure in YAML")
            self._prompts: Dict[str, Dict[str, Any]] = prompts
        except FileNotFoundError:
            self._prompts = {}
        except (yaml.YAMLError, ValueError) as e:
            # Handle cases of malformed YAML or incorrect structure
            raise ValueError(f"Failed to load or parse prompts.yaml: {e}") from e

    def get_prompt(self, name: str) -> Dict[str, Any]:
        """Return the prompt dictionary for the given name."""
        try:
            return self._prompts[name]
        except KeyError as exc:
            raise KeyError(f"Prompt '{name}' not found") from exc


__all__ = ["PromptManager"]
