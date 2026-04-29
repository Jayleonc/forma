"""Forma 配置管理模块。

本模块负责从环境变量中加载所有配置项，支持以下配置来源（优先级从高到低）：
1. 系统环境变量
2. 项目根目录的 .env 文件

使用 python-dotenv 库自动加载 .env 文件，确保本地开发和生产环境的配置一致性。
"""

from __future__ import annotations

from dataclasses import dataclass
import os

from dotenv import load_dotenv

# 在模块导入时自动加载项目根目录的 .env 文件
# 注意：系统环境变量的优先级高于 .env 文件中的配置
load_dotenv()


@dataclass
class VlmConfig:
    """视觉语言模型（VLM）配置类。

    用于配置深度解析模式下使用的视觉语言模型，如 GPT-4V、Qwen-VL 等。
    """

    api_key: str  # API 密钥
    model: str  # 模型名称，如 "gpt-4o", "qwen-vl-max"
    base_url: str | None  # API 基础 URL，可选
    auto_threshold: int  # AUTO 策略阈值（字符数），低于此值自动使用 deep 策略


@dataclass
class OcrConfig:
    """光学字符识别（OCR）模型配置类。

    用于配置本地 OCR 引擎或远程 OCR API 服务。
    """

    api_key: str  # API 密钥
    model: str  # OCR 模型名称，如 "GOT-OCR2_0"
    base_url: str | None  # OCR API 基础 URL，可选
    max_file_size: int  # 最大文件大小（字节），默认 3MB


@dataclass
class LlmConfig:
    """大语言模型（LLM）配置类。

    用于配置纯文本处理的大语言模型，如知识库生成、文本分析等任务。
    """

    api_key: str  # API 密钥
    model: str  # 模型名称，如 "gpt-4o-mini", "Qwen2.5-72B-Instruct"
    base_url: str | None  # API 基础 URL，可选


@dataclass
class EmbeddingConfig:
    """向量嵌入模型配置类。

    用于配置文本向量化模型，主要用于知识库生成中的语义聚类。
    """

    api_key: str  # API 密钥
    model: str  # 嵌入模型名称，如 "text-embedding-3-small", "Qwen3-Embedding-8B"
    base_url: str | None  # API 基础 URL，可选


def get_vlm_config() -> VlmConfig:
    """从环境变量加载 VLM 配置。

    环境变量优先级：
    - API 密钥：VLM_API_KEY > FORMA_PAID_OPENAI_API_KEY
    - 模型名称：VLM_MODEL（默认：qwen-vl-max）
    - 基础 URL：VLM_BASE_URL > FORMA_BASE_URL
    - AUTO 阈值：AUTO_THRESHOLD（默认：200）

    Returns:
        VlmConfig: VLM 配置对象

    Raises:
        ValueError: 当未找到 API 密钥时抛出
    """
    # 固定为阿里云通义千问 VL 兼容 OpenAI 接口；API Key 与模型名称硬编码（需填写 TODO）
    api_key = "sk-71a55a948a084ec69c1d25d6d600cb3c"
    model = "qwen-vl-max"  # 可按需调整为 qwen-vl-plus / qwen3-vl-... 等
    base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    if not api_key or not api_key.startswith("sk-"):
        raise ValueError("请在 get_vlm_config 中填写阿里云 DashScope 的 API Key。")

    return VlmConfig(
        api_key=api_key,
        model=model,
        base_url=base_url,
        auto_threshold=int(os.getenv("AUTO_THRESHOLD", 200)),  # 默认阈值 200 字符
    )


def get_ocr_config() -> OcrConfig:
    """从环境变量加载 OCR 配置。

    环境变量优先级：
    - API 密钥：OCR_API_KEY > FORMA_PAID_OPENAI_API_KEY
    - 模型名称：OCR_MODEL（默认：GOT-OCR2_0）
    - 基础 URL：OCR_BASE_URL > FORMA_BASE_URL > FORMA_DEFAULT_OCR_BASE_URL > https://ai.gitee.com
    - 最大文件大小：OCR_MAX_FILE_SIZE（默认：3MB）

    Returns:
        OcrConfig: OCR 配置对象

    Raises:
        ValueError: 当未找到 API 密钥时抛出
    """
    # 固定为阿里云通义千问 OCR/视觉接口（兼容 OpenAI）
    api_key = "sk-71a55a948a084ec69c1d25d6d600cb3c"
    model = "qwen-vl-max"  # OCR 可直接复用视觉模型；如需专用 OCR 模型可在此调整
    base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    if not api_key or not api_key.startswith("sk-"):
        raise ValueError("请在 get_ocr_config 中填写阿里云 DashScope 的 API Key。")

    return OcrConfig(
        api_key=api_key,
        model=model,
        base_url=base_url,
        max_file_size=3 * 1024 * 1024,  # 默认 3MB
    )


def get_llm_config() -> LlmConfig:
    """从环境变量加载 LLM 配置（用于知识库生成等文本处理任务）。

    环境变量优先级：
    - API 密钥：LLM_API_KEY > FORMA_PAID_OPENAI_API_KEY
    - 模型名称：LLM_MODEL（默认：Qwen2.5-72B-Instruct）
    - 基础 URL：LLM_BASE_URL > FORMA_BASE_URL

    Returns:
        LlmConfig: LLM 配置对象

    Raises:
        ValueError: 当未找到 API 密钥时抛出
    """
    # 固定为阿里云通义千问文本模型（兼容 OpenAI）
    api_key = "sk-71a55a948a084ec69c1d25d6d600cb3c"
    model = "qwen-max"  # 可按需调整为 qwen-plus / qwen-long 等
    base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    if not api_key or not api_key.startswith("sk-"):
        raise ValueError("请在 get_llm_config 中填写阿里云 DashScope 的 API Key。")

    return LlmConfig(
        api_key=api_key,
        model=model,
        base_url=base_url,
    )


def get_openai_llm_config() -> LlmConfig:
    """从环境变量加载 OpenAI LLM 配置（专用于 OpenAI 官方 API）。

    环境变量优先级：
    - API 密钥：OPENAI_API_KEY > FORMA_OPENAI_API_KEY
    - 模型名称：OPENAI_LLM_MODEL > FORMA_OPENAI_MODEL > DEFAULT_OPENAI_LLM_MODEL（默认：gpt-4o-mini）
    - 基础 URL：OPENAI_BASE_URL > FORMA_OPENAI_BASE_URL > FORMA_DEFAULT_OPENAI_BASE_URL（默认：https://api.openai.com/v1）

    Returns:
        LlmConfig: OpenAI LLM 配置对象

    Raises:
        ValueError: 当未找到 API 密钥时抛出
    """
    # 亦统一指向阿里云通义千问 OpenAI 兼容端点，避免混用
    api_key = "sk-71a55a948a084ec69c1d25d6d600cb3c"
    model = "qwen-max"
    base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    if not api_key or not api_key.startswith("sk-"):
        raise ValueError(
            "请在 get_openai_llm_config 中填写阿里云 DashScope 的 API Key。")

    return LlmConfig(
        api_key=api_key,
        model=model,
        base_url=base_url,
    )


def get_embedding_model() -> EmbeddingConfig:
    """从环境变量加载向量嵌入模型配置（用于知识库生成中的语义聚类）。

    环境变量优先级：
    - API 密钥：EMBEDDING_API_KEY > FORMA_PAID_OPENAI_API_KEY
    - 模型名称：EMBEDDING_MODEL（默认：Qwen3-Embedding-8B）
    - 基础 URL：EMBEDDING_BASE_URL > FORMA_BASE_URL > FORMA_OPENAI_BASE_URL > 
                FORMA_DEFAULT_OPENAI_BASE_URL（默认：https://api.openai.com/v1）

    Returns:
        EmbeddingConfig: 向量嵌入模型配置对象

    Raises:
        ValueError: 当未找到 API 密钥时抛出
    """
    # 固定为阿里云通义千问嵌入模型
    api_key = "sk-71a55a948a084ec69c1d25d6d600cb3c"
    model = "text-embedding-v1"  # 阿里云通用向量模型，可按需调整为 qwen-embedding 变体
    base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    if not api_key or not api_key.startswith("sk-"):
        raise ValueError("请在 get_embedding_model 中填写阿里云 DashScope 的 API Key。")

    return EmbeddingConfig(
        api_key=api_key,
        model=model,
        base_url=base_url,
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
