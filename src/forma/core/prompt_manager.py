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
    `knowledge_distillation` 和 `theme_synthesis` 任务需要严格的 JSON 结构，因此使用了 `OutputParser`，
    并在代码中拼接了 `{format_instructions}` 变量。
    而 `theme_generation_prompt` 任务的输出格式较简单，未使用 `OutputParser`，因此其白名单中不包含此变量。
    """

    _ALLOWED_VARS_MAP = {
        "knowledge_distillation_prompt": {"chunk_text", "format_instructions"},
        "theme_generation_prompt": {"enriched_chunks"},
        "theme_synthesis_prompt": {
            "theme",
            "related_knowledge",
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

            self._prompts: Dict[str, Dict[str, Any]] = {}
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
        except FileNotFoundError:
            self._prompts = {}
        except (yaml.YAMLError, ValueError) as e:
            # Handle cases of malformed YAML or incorrect structure
            raise ValueError(
                f"Failed to load or parse prompts.yaml: {e}") from e

    def get_prompt(self, name: str) -> Dict[str, Any]:
        """Return the prompt dictionary for the given name."""
        try:
            return self._prompts[name]
        except KeyError as exc:
            raise KeyError(f"Prompt '{name}' not found") from exc


__all__ = ["PromptManager"]
