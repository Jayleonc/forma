"""Prompt management for VLM prompts loaded from YAML."""

from __future__ import annotations

from pathlib import Path
from threading import Lock
from typing import Any, Dict

import yaml


class PromptManager:
    """Thread-safe singleton manager for loading and sanitizing prompts from a YAML file."""

    """
    --- 动态变量白名单 (Dynamic Variable Whitelist) ---
    
    [核心问题]
    LangChain 的提示词模板 (ChatPromptTemplate) 会将任何用单花括号 `{}` 包起来的文字都当作一个动态变量。
    例如，在我们的提示词中，既包含我们希望 AI 遵循的 JSON 格式示例，如 `{"summary": "..."}`，
    也包含真正的动态变量，如 `{chunk_text}`，我们希望在运行时填充它。
    如果不加处理，LangChain 会错误地将 JSON 示例中的 `{"summary":...}` 也识别为需要填充的变量，
    从而在运行时因找不到对应的输入值而抛出“缺少变量”的错误。
    
    [解决方案]
    我们在加载 YAML 提示词时，采用“先全部转义，再按白名单恢复”的策略：
    1. 全部转义：将所有单花括号 `{}` 替换为双花括号 `{{}}`。这会告诉 LangChain 忽略它们。
    2. 按白名单恢复：对于每个提示词，我们定义一个“白名单”（即本字典），其中只包含真正的动态变量。
       程序会遍历白名单，将这些真变量从双花括号恢复为单花括号，例如 `{{chunk_text}}` -> `{chunk_text}`。
    
    [特例说明：`format_instructions`]
    注意，`format_instructions` 出现在某些提示词的白名单中，但并未在 YAML 文件中定义。
    这是因为它是一个由 LangChain 的 `OutputParser` 在代码中动态生成的变量，用于指示输出格式。
    `knowledge_distillation` 和 `global_knowledge_synthesis` 任务需要严格的 JSON 结构，因此使用了 `OutputParser`，
    并在代码中拼接了 `{format_instructions}` 变量。
    """

    _ALLOWED_VARS_MAP = {
        # 图像描述相关提示词
        "default_image_description": set(),  # 无变量
        "docx_image_description": set(),     # 无变量
        "pdf_image_description": set(),      # 无变量
        
        # 知识提取相关提示词
        "knowledge_distillation_prompt": {"chunk_text", "format_instructions"},
        "global_knowledge_synthesis_prompt": {"enriched_chunks", "format_instructions"},
        # Allow variables for hierarchical prompt so placeholders are substituted correctly
        "hierarchical_knowledge_distillation_prompt": {
            "chunk_text",
            "header_chain",
            "parent_summary",
            "preferred_language_instruction",
            "format_instructions",
        },
    }

    _instance: "PromptManager | None" = None
    _lock = Lock()

    def __new__(cls) -> "PromptManager":
        if cls._instance is None:
            with cls._lock:
                # Double-check locking to prevent race conditions
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    # 初始化一个空的 _prompts 字典，确保即使 _load_prompts 失败也能有这个属性
                    cls._instance._prompts = {}
                    cls._instance._load_prompts()
        return cls._instance

    @staticmethod
    def _sanitize_template(text: str, allowed_vars: set[str]) -> str:
        """转义模板中所有非法的花括号变量。"""
        # 1. 将所有单花括号替换为双花括号，以进行转义
        sanitized = text.replace("{", "{{").replace("}", "}}")
        # 2. 恢复允许的变量，将双花括号转义还原为单花括号
        for var in allowed_vars:
            sanitized = sanitized.replace(f"{{{{{var}}}}}", f"{{{var}}}")
        return sanitized

    def _load_prompts(self) -> None:
        """Load and sanitize prompts from the YAML file."""
        try:
            root = Path(__file__).resolve().parent.parent.parent.parent
            path = root / "prompts.yaml"
            with path.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            raw_prompts = data.get("prompts") or {}
            if not isinstance(raw_prompts, dict):
                raise ValueError("Invalid 'prompts' structure in YAML")

            # 清空并重新填充 _prompts 字典
            self._prompts.clear()
            for name, template in raw_prompts.items():
                allowed_vars = self._ALLOWED_VARS_MAP.get(name, set())
                self._prompts[name] = {
                    "system": self._sanitize_template(
                        template.get("system", ""), set()
                    ),
                    "user": self._sanitize_template(
                        template.get("user", ""), allowed_vars
                    ),
                }
            
            # 打印已加载的提示词列表
            print(f"[DEBUG] Successfully loaded {len(self._prompts)} prompts: {', '.join(self._prompts.keys())}")
            
            # 检查是否有关键提示词缺失
            key_prompts = ["default_image_description", "pdf_image_description", "docx_image_description"]
            missing_prompts = [p for p in key_prompts if p not in self._prompts]
            if missing_prompts:
                print(f"[WARNING] Some key prompts are missing: {', '.join(missing_prompts)}")
            else:
                print(f"[DEBUG] All key prompts are loaded successfully.")
        except FileNotFoundError:
            # 文件不存在时，保持 _prompts 为空字典
            print(f"[WARNING] prompts.yaml file not found at {root / 'prompts.yaml'}")
            # self._prompts 已在 __new__ 中初始化为空字典
        except (yaml.YAMLError, ValueError) as e:
            # 处理 YAML 格式错误或结构不正确的情况
            print(f"[ERROR] Failed to load or parse prompts.yaml: {e}")
            # 保持 _prompts 为空字典，而不是抛出异常
        except Exception as e:
            # 捕获所有其他异常，确保不会影响程序的正常运行
            print(f"[ERROR] Unexpected error when loading prompts.yaml: {e}")
            # self._prompts 已在 __new__ 中初始化为空字典

    def get_prompt(self, name: str) -> Dict[str, Any]:
        """Return the prompt dictionary for the given name."""
        try:
            return self._prompts[name]
        except KeyError as exc:
            raise KeyError(f"Prompt '{name}' not found") from exc


__all__ = ["PromptManager"]
