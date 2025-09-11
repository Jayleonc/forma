"""Processor for image files."""

from __future__ import annotations

from pathlib import Path

from .base import ProcessingResult, Processor
from ...ocr import parse_image_to_markdown
from ...vision import VlmParser
from ...shared.custom_types import Strategy


class ImageProcessor(Processor):
    """Processor for image files using OCR."""

    def process(self, input_path: Path) -> ProcessingResult:
        """使用 OCR/版面结构解析（PP-Structure）处理图片，生成 Markdown。

        说明：这是 FAST 策略下的默认实现；在更高层策略（AUTO/DEEP）下，通常会优先选择 VLM。
        """
        md = parse_image_to_markdown(str(input_path))
        text_len = len(md.strip())
        return ProcessingResult(
            markdown_content=md,
            text_char_count=text_len,
            image_count=1,
            low_confidence=text_len == 0,
        )

    # 说明：
    # 为了提升可读性与内聚性，这里增加一个“基于 VLM 的图片解析”辅助方法，
    # 仅负责调用 VLM 解析并返回 Markdown 文本；不承担清洗与写文件职责。
    # 这样可以让与图片解析相关的逻辑集中在 ImageProcessor 内部，
    # 同时不对 workflow 中的特殊分支进行完整迁移，避免大范围重构。
    def vlm_parse(self, input_path: Path, vlm_parser: VlmParser, *, prompt_name: str = "default_image_description") -> str:
        """使用 VLM 对图片进行解析，返回原始 Markdown 文本。

        注意：
        - 不在此方法中做 Markdown 清洗与写文件操作，保持职责单一；
        - 由上层（workflow）在拿到 Markdown 后继续做清洗/落盘。
        """
        # 直接委托给 VLM 解析器
        return vlm_parser.parse(input_path, prompt_name=prompt_name)

    def process_with_strategy(
        self,
        input_path: Path,
        strategy: Strategy,
        vlm_parser: VlmParser | None = None,
        *,
        prompt_name: str = "default_image_description",
    ) -> str:
        """根据策略选择解析路径，返回原始（未清洗）的 Markdown 文本。

        - AUTO/DEEP：使用 VLM（需要传入 vlm_parser）
        - FAST：使用 OCR（fallback 到 process())

        仅负责解析，不负责清洗与写文件。
        """
        if strategy in (Strategy.AUTO, Strategy.DEEP):
            if not vlm_parser:
                raise ValueError("AUTO/DEEP 策略需要提供 vlm_parser")
            return self.vlm_parse(input_path, vlm_parser, prompt_name=prompt_name)
        # FAST 策略：走 OCR/PP-Structure
        return self.process(input_path).markdown_content

__all__ = ["ImageProcessor"]
