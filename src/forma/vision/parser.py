"""Abstraction layer for vision-language model parsing."""

from __future__ import annotations

from pathlib import Path
from typing import List
import logging
import tempfile

from .client import OpenAIVLMClient, VLMClient
from ..shared.prompts import PromptManager


logger = logging.getLogger(__name__)


class VlmParser:
    """Wrapper for VLM processing, handling file-type-specific logic."""

    def __init__(self, vlm_client: VLMClient | None = None) -> None:
        self.client = vlm_client or OpenAIVLMClient()
        self.prompt_manager = PromptManager()

    def parse(self, path: Path, prompt_name: str = "default_image_description") -> str:
        """Parse an image or PDF via the VLM service and return Markdown text."""

        prompt = self.prompt_manager.get_prompt(prompt_name)

        if path.suffix.lower() == ".pdf":
            image_paths: List[Path] = []
            import fitz

            doc = fitz.open(str(path))
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp = Path(tmpdir)
                for i, page in enumerate(doc):
                    pix = page.get_pixmap()
                    
                    # 检查图像尺寸，忽略太小的图像
                    if pix.width < 30 or pix.height < 30:  # 设置一个安全的最小尺寸
                        logger.info(
                            "Page %s is too small: %sx%s, skipping",
                            i,
                            pix.width,
                            pix.height,
                        )
                        continue
                        
                    img_path = tmp / f"page_{i}.png"
                    pix.save(str(img_path))
                    image_paths.append(img_path)
                doc.close()
                
                # 如果没有有效的图像，返回空字符串
                if not image_paths:
                    return ""
                    
                return self.client.invoke(image_paths, prompt)
        else:
            # 对于单个图像文件，也应该进行尺寸检查
            try:
                from PIL import Image
                with Image.open(path) as img:
                    width, height = img.size
                    if width < 30 or height < 30:
                        logger.info(
                            "Image is too small: %sx%s, skipping", width, height
                        )
                        return ""
            except ImportError:
                # 如果没有安装 PIL，跳过检查
                logger.warning("PIL not installed, skipping image size check")
            except Exception as e:
                # 如果检查失败，记录警告但继续处理
                logger.warning("Failed to check image size: %s", e)
                
            return self.client.invoke([path], prompt)


__all__ = ["VlmParser"]
