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
class OcrConfig:
    """Configuration for OCR models."""

    api_key: str
    model: str
    base_url: str | None
    max_file_size: int  # 最大文件大小（字节）


@dataclass
class LlmConfig:
    """Configuration for Large Language Models (text-only)."""

    api_key: str
    model: str
    base_url: str | None


@dataclass
class EmbeddingConfig:
    """Configuration for Embedding models (e.g., OpenAI embeddings)."""

    api_key: str
    model: str
    base_url: str | None


def get_vlm_config() -> VlmConfig:
    """Load VLM related configuration from environment variables."""
    api_key = os.getenv("VLM_API_KEY") or os.getenv(
        "FORMA_PAID_OPENAI_API_KEY")
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


def get_ocr_config() -> OcrConfig:
    """Load OCR related configuration from environment variables."""
    # 使用与VLM相同的API密钥配置
    api_key = os.getenv("OCR_API_KEY") or os.getenv(
        "FORMA_PAID_OPENAI_API_KEY")
    if not api_key:
        raise ValueError(
            "API key not found. Please set OCR_API_KEY or FORMA_PAID_OPENAI_API_KEY."
        )

    # 默认使用GOT-OCR2_0模型
    return OcrConfig(
        api_key=api_key,
        model=os.getenv("OCR_MODEL", "GOT-OCR2_0"),
        base_url=(
            os.getenv("OCR_BASE_URL")
            or os.getenv("FORMA_BASE_URL")
            or os.getenv("FORMA_DEFAULT_OCR_BASE_URL")
            or "https://ai.gitee.com"
        ),
        max_file_size=int(os.getenv("OCR_MAX_FILE_SIZE",
                          3 * 1024 * 1024)),  # 默认3MB
    )


def get_llm_config() -> LlmConfig:
    """Load LLM related configuration from environment variables."""
    api_key = os.getenv("LLM_API_KEY") or os.getenv(
        "FORMA_PAID_OPENAI_API_KEY")
    if not api_key:
        raise ValueError(
            "API key not found. Please set LLM_API_KEY or FORMA_PAID_OPENAI_API_KEY."
        )

    return LlmConfig(
        api_key=api_key,
        # 从环境变量读取模型名称，默认使用更小更快的模型
        model=os.getenv("LLM_MODEL", "Qwen2.5-72B-Instruct"),
        base_url=os.getenv("LLM_BASE_URL") or os.getenv("FORMA_BASE_URL"),
    )


def get_openai_llm_config() -> LlmConfig:
    """Load OpenAI LLM configuration from environment variables."""

    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("FORMA_OPENAI_API_KEY")
    if not api_key:
        raise ValueError(
            "API key not found. Please set OPENAI_API_KEY or FORMA_OPENAI_API_KEY."
        )

    model = os.getenv("OPENAI_LLM_MODEL") or os.getenv("FORMA_OPENAI_MODEL")
    if not model:
        model = os.getenv("DEFAULT_OPENAI_LLM_MODEL", "gpt-4o-mini")

    base_url = os.getenv("OPENAI_BASE_URL") or os.getenv("FORMA_OPENAI_BASE_URL")
    if not base_url:
        base_url = (
            os.getenv("FORMA_DEFAULT_OPENAI_BASE_URL")
            or "https://api.openai.com/v1"
        )

    return LlmConfig(
        api_key=api_key,
        model=model,
        base_url=base_url,
    )


def get_embedding_model() -> EmbeddingConfig:
    """Load Embedding model configuration (defaults to OpenAI embeddings).

    Environment variables:
    - EMBEDDING_API_KEY or FORMA_PAID_OPENAI_API_KEY
    - EMBEDDING_MODEL (default: text-embedding-3-small)
    - EMBEDDING_BASE_URL (default: https://api.openai.com/v1)
    """
    api_key = (
        os.getenv("EMBEDDING_API_KEY")
        or os.getenv("FORMA_PAID_OPENAI_API_KEY")
    )
    if not api_key:
        raise ValueError(
            "Embedding API key not found. Please set EMBEDDING_API_KEY or FORMA_PAID_OPENAI_API_KEY."
        )

    return EmbeddingConfig(
        api_key=api_key,
        model=os.getenv("EMBEDDING_MODEL", "Qwen3-Embedding-8B"),
        base_url=(
            os.getenv("EMBEDDING_BASE_URL")
            or os.getenv("FORMA_BASE_URL")
            or os.getenv("FORMA_OPENAI_BASE_URL")
            or os.getenv("FORMA_DEFAULT_OPENAI_BASE_URL")
            or "https://api.openai.com/v1"
        ),
    )


__all__ = [
    "VlmConfig",
    "get_vlm_config",
    "OcrConfig",
    "get_ocr_config",
    "LlmConfig",
    "get_llm_config",
    "get_openai_llm_config",
    "EmbeddingConfig",
    "get_embedding_model",
]
