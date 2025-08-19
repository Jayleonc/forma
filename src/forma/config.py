"""Configuration helpers for forma."""

from __future__ import annotations

from dataclasses import dataclass
import os

from dotenv import load_dotenv

# Load .env file at the application's entry point
load_dotenv()


@dataclass
class VlmConfig:
    """Configuration for the Vision Language Model."""

    api_key: str
    model: str
    base_url: str | None = None
    auto_threshold: int = 200


def get_vlm_config() -> VlmConfig:
    """Load VLM related configuration from environment variables."""
    api_key = os.getenv("FORMA_OPENAI_API_KEY")
    if not api_key:
        raise ValueError(
            "API key not found. Please set FORMA_OPENAI_API_KEY in your .env file."
        )

    return VlmConfig(
        api_key=api_key,
        model=os.getenv("VLM_MODEL", "qwen-vl-max"),
        base_url=os.getenv("FORMA_BASE_URL"),
        auto_threshold=int(os.getenv("AUTO_THRESHOLD", 200)),
    )


__all__ = ["VlmConfig", "get_vlm_config"]
