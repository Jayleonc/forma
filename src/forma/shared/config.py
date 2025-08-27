"""Configuration helpers for forma."""

from __future__ import annotations

from dataclasses import dataclass
import os

from dotenv import load_dotenv

# Load .env file at the application's entry point
load_dotenv()


@dataclass
class VlmConfig:
    """Configuration for Vision Language Models."""

    api_key: str
    model: str
    base_url: str | None
    auto_threshold: int


@dataclass
class LlmConfig:
    """Configuration for Large Language Models (text-only)."""

    api_key: str
    model: str
    base_url: str | None


def get_vlm_config() -> VlmConfig:
    """Load VLM related configuration from environment variables."""
    api_key = os.getenv("VLM_API_KEY") or os.getenv("FORMA_OPENAI_API_KEY")
    if not api_key:
        raise ValueError(
            "API key not found. Please set VLM_API_KEY or FORMA_PAID_OPENAI_API_KEY."
        )

    return VlmConfig(
        api_key=api_key,
        model=os.getenv("VLM_MODEL", "qwen-vl-max"),
        base_url=os.getenv("VLM_BASE_URL") or os.getenv("FORMA_BASE_URL"),
        auto_threshold=int(os.getenv("AUTO_THRESHOLD", 200)),
    )


def get_llm_config() -> LlmConfig:
    """Load LLM related configuration from environment variables."""
    api_key = os.getenv("LLM_API_KEY") or os.getenv("FORMA_OPENAI_API_KEY")
    if not api_key:
        raise ValueError(
            "API key not found. Please set LLM_API_KEY or FORMA_PAID_OPENAI_API_KEY."
        )

    return LlmConfig(
        api_key=api_key,
        # model=os.getenv("LLM_MODEL", "Qwen3-32B"),
        model="Qwen2.5-72B-Instruct",
        base_url=os.getenv("LLM_BASE_URL") or os.getenv("FORMA_BASE_URL"),
    )


def get_openai_llm_config() -> LlmConfig:
    """Load LLM related configuration from environment variables."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError(
            "API key not found. Please set OPENAI_API_KEY or FORMA_OPENAI_API_KEY."
        )

    return LlmConfig(
        api_key=api_key,
        model="gpt-4o-mini",
        base_url="https://api.openai.com/v1",
    )


__all__ = ["VlmConfig", "get_vlm_config", "LlmConfig", "get_llm_config"]
