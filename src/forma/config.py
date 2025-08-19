"""Configuration helpers for forma."""

from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass
class VlmConfig:
    api_key: str
    base_url: str | None = None
    model: str | None = None


def get_vlm_config() -> VlmConfig:
    """Load VLM related configuration from environment variables."""

    return VlmConfig(
        api_key=os.getenv("VLM_API_KEY", ""),
        base_url=os.getenv("VLM_BASE_URL"),
        model=os.getenv("VLM_MODEL", "gpt-4o-mini"),
    )


__all__ = ["VlmConfig", "get_vlm_config"]
