"""Workflow module for document conversion.

This was extracted from the previous `controller.py` to separate concerns.
Exposes a single public helper `run_conversion` used by the CLI.
"""

from __future__ import annotations
import os
import re
import shutil
import time
from enum import Enum
from pathlib import Path
from typing import List, Optional, Union

from ..shared.utils.timeout import timeout, TimeoutError
from ..vision import OpenAIVLMClient, VlmParser, VLMClient
from ..shared.custom_types import Strategy
from .processors import (
    DocxProcessor,
    ImageProcessor,
    PdfProcessor,
    PptxProcessor,
    Processor,
    ProcessingResult,
)
from ..shared.utils.markdown_cleaner import MarkdownCleaner
from ..shared.config import get_vlm_config

THRESHOLD = get_vlm_config().auto_threshold

__all__ = ["run_conversion"]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_conversion(
    inputs: List[Path],
    output_dir: Path,
    strategy: Strategy,
    recursive: bool,
    prompt_name: str = "default_image_description",
    output_name: str | None = None,
    use_ocr_for_images: bool = False,
) -> None:
    """Entry point invoked by the CLI.

    Parameters
    ----------
    inputs: List[Path]
        Files or directories to process.
    output_dir: Path
        Output directory to place markdown files.
    strategy: Strategy
        Conversion strategy: AUTO | FAST | DEEP
    recursive: bool
        Whether to recurse into sub-directories.
    prompt_name: str, optional
        Prompt name for deep strategy, by default "default_image_description".
    """

    files = _discover_files(inputs, recursive)
    output_dir.mkdir(parents=True, exist_ok=True)

    vlm_client: VLMClient | None = None
    if strategy != Strategy.FAST:
        vlm_client = OpenAIVLMClient()

    vlm_parser = VlmParser(vlm_client) if strategy != Strategy.FAST else None

    # If a custom output name is provided and there's only one file, use it.
    # Otherwise, this parameter is ignored.
    effective_output_name = output_name if len(files) == 1 else None

    for path in files:
        _process_single_file(
            path,
            output_dir,
            strategy,
            vlm_parser,
            vlm_client,
            prompt_name,
            effective_output_name,
            use_ocr_for_images,
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _discover_files(inputs: List[Path], recursive: bool) -> List[Path]:
    files: List[Path] = []
    for inp in inputs:
        if inp.is_file():
            files.append(inp)
        elif inp.is_dir():
            iterator = inp.rglob("*") if recursive else inp.glob("*")
            for p in iterator:
                if p.is_file():
                    files.append(p)
    return files


def _select_processor(path: Path, vlm_client: VLMClient | None, use_ocr_for_images: bool = False) -> Processor | None:
    suffix = path.suffix.lower()
    print(f"[DEBUG] Selecting processor for file: {path}, suffix: {suffix}")

    # 基于文件后缀名选择处理器
    if suffix == ".pdf":
        print(
            f"[DEBUG] Selected PdfProcessor for {path} based on suffix, use_ocr={use_ocr_for_images}")
        return PdfProcessor(vlm_client=vlm_client, use_ocr=use_ocr_for_images)
    if suffix in {".png", ".jpg", ".jpeg", ".bmp"}:
        print(f"[DEBUG] Selected ImageProcessor for {path} based on suffix")
        return ImageProcessor()
    if suffix == ".docx":
        print(f"[DEBUG] Selected DocxProcessor for {path} based on suffix")
        return DocxProcessor(vlm_client=vlm_client)
    if suffix == ".pptx":
        print(f"[DEBUG] Selected PptxProcessor for {path} based on suffix")
        return PptxProcessor(vlm_client=vlm_client)

    # 如果没有后缀名或后缀名不匹配，尝试基于文件内容检测类型
    print(
        f"[INFO] Attempting to detect file type based on content for: {path}")
    try:
        # 读取文件头部字节用于检测文件类型
        with open(path, 'rb') as f:
            header = f.read(8)  # 读取前8个字节

        # PDF文件头部特征: %PDF
        if header.startswith(b'%PDF'):
            print(
                f"[DEBUG] Detected PDF file based on content signature for {path}")
            return PdfProcessor()

        # DOCX文件头部特征: PK (ZIP格式)
        elif header.startswith(b'PK'):
            # 这可能是DOCX或PPTX (都是ZIP格式)
            # 进一步检查文件大小和其他特征可以区分它们
            # 这里简单地假设它是DOCX
            print(
                f"[DEBUG] Detected Office document (possibly DOCX/PPTX) based on content signature for {path}")
            return DocxProcessor(vlm_client=vlm_client)

        # 图像文件头部特征
        elif header.startswith(b'\xff\xd8'):  # JPEG
            print(
                f"[DEBUG] Detected JPEG image based on content signature for {path}")
            return ImageProcessor()
        elif header.startswith(b'\x89PNG'):  # PNG
            print(
                f"[DEBUG] Detected PNG image based on content signature for {path}")
            return ImageProcessor()
        elif header.startswith(b'GIF8'):  # GIF
            print(
                f"[DEBUG] Detected GIF image based on content signature for {path}")
            return ImageProcessor()
        elif header.startswith(b'BM'):  # BMP
            print(
                f"[DEBUG] Detected BMP image based on content signature for {path}")
            return ImageProcessor()

    except Exception as e:
        print(
            f"[ERROR] Error during file type detection: {e.__class__.__name__}: {e}")

    print(
        f"[WARNING] No processor found for file: {path} with suffix: {suffix}")
    return None


def _process_single_file(
    path: Path,
    output_dir: Path,
    strategy: Strategy,
    vlm_parser: VlmParser | None = None,
    vlm_client: VLMClient | None = None,
    prompt_name: str = "default_image_description",
    output_name: str | None = None,
    use_ocr_for_images: bool = False,
) -> None:
    print(
        f"[DEBUG] Processing file: {path}, strategy: {strategy}, use_ocr_for_images: {use_ocr_for_images}")
    processor = _select_processor(path, vlm_client, use_ocr_for_images)
    if processor is None:
        print(f"[ERROR] No suitable processor found for {path}, skipping file")
        return

    print(f"[DEBUG] Using processor: {processor.__class__.__name__}")
    stem = output_name if output_name else path.stem
    output_path = output_dir / f"{stem}.md"
    print(f"[DEBUG] Output will be written to: {output_path}")

    # 图片文件统一由处理器内部根据策略决定使用 VLM 还是 OCR，
    # workflow 只做业务聚合（清洗与落盘）。
    if isinstance(processor, ImageProcessor):
        print(f"[DEBUG] ImageProcessor will decide path by strategy: {strategy}")
        # 对于 AUTO/DEEP，若未提供 vlm_parser，这里创建一个以便传入处理器
        if strategy in (Strategy.AUTO, Strategy.DEEP) and not vlm_parser:
            print(f"[DEBUG] Creating VlmParser for image processing (strategy={strategy})")
            vlm_parser = VlmParser(vlm_client)
        markdown = processor.process_with_strategy(
            path, strategy, vlm_parser, prompt_name=prompt_name
        )
        cleaned_markdown = MarkdownCleaner.clean_markdown(markdown)
        print(
            f"[DEBUG] Writing cleaned image result to {output_path}, content length: {len(cleaned_markdown)}")
        output_path.write_text(cleaned_markdown, encoding="utf-8")
        return

    # TODO 这里可以优化，非图片的DEEP，直接走VLM，是不是不对呢。。。。
    if strategy == Strategy.DEEP:
        print(f"[DEBUG] Using DEEP strategy for {path}")
        if not vlm_parser:
            print(f"[DEBUG] Creating VlmParser for deep processing")
            vlm_parser = VlmParser(vlm_client)
        print(f"[DEBUG] Parsing file with VLM: {path}")
        # 非图片类型在 DEEP 策略下走通用 VLM 解析
        markdown = vlm_parser.parse(path, prompt_name=prompt_name)
        # 应用Markdown清洗
        cleaned_markdown = MarkdownCleaner.clean_markdown(markdown)
        print(
            f"[DEBUG] Writing cleaned VLM result to {output_path}, content length: {len(cleaned_markdown)}")
        output_path.write_text(cleaned_markdown, encoding="utf-8")
        return

    print(
        f"[DEBUG] Using standard processor for {path}: {processor.__class__.__name__}")
    try:
        # 添加超时机制，最长处理时间为300秒（5分钟）
        @timeout(300)
        def process_with_timeout(processor, path):
            start_time = time.time()
            result = processor.process(path)
            elapsed = time.time() - start_time
            print(
                f"[DEBUG] Processing completed in {elapsed:.2f}s, text length: {result.text_char_count}, low confidence: {result.low_confidence}")
            return result

        result = None
        final_md = None
        
        try:
            result: ProcessingResult = process_with_timeout(processor, path)
            final_md = result.markdown_content
        except TimeoutError:
            print(
                f"[ERROR] Processing timed out after 300 seconds for {path}, falling back to simpler method")
            # 如果超时，可以尝试使用更简单的处理方法
            if isinstance(processor, PdfProcessor) and hasattr(processor, "_use_ocr"):
                # 对于PDF处理器，可以切换到仅使用OCR模式
                print(f"[DEBUG] Retrying with OCR-only mode for PDF")
                processor._use_ocr = True
                result = processor.process(path)
                final_md = result.markdown_content
            else:
                # 对于其他处理器，如果有VLM可用，直接使用VLM
                if vlm_client:
                    print(f"[DEBUG] Falling back to VLM due to timeout")
                    if not vlm_parser:
                        vlm_parser = VlmParser(vlm_client)
                    final_md = vlm_parser.parse(path, prompt_name=prompt_name)
                    # 创建一个虚拟result对象，避免后面的代码出错
                    result = ProcessingResult(
                        markdown_content=final_md,
                        text_char_count=len(final_md),
                        image_count=0,
                        low_confidence=False
                    )
                else:
                    raise  # 如果没有可用的备选方案，重新抛出超时异常

        # For AUTO mode on other file types, use confidence score to decide.
        if result and strategy == Strategy.AUTO and (
            result.low_confidence or result.text_char_count < THRESHOLD
        ):
            print(
                f"[DEBUG] Low confidence or text below threshold ({result.text_char_count} < {THRESHOLD}), using VLM")
            if not vlm_parser:
                print(f"[DEBUG] Creating VlmParser for fallback processing")
                vlm_parser = VlmParser(vlm_client)
            print(f"[DEBUG] Parsing with VLM as fallback: {path}")
            final_md = vlm_parser.parse(path, prompt_name=prompt_name)

        # 应用Markdown清洗
        cleaned_final_md = MarkdownCleaner.clean_markdown(final_md)
        print(
            f"[DEBUG] Writing cleaned final result to {output_path}, content length: {len(cleaned_final_md)}")
        output_path.write_text(cleaned_final_md, encoding="utf-8")
    except Exception as e:
        print(
            f"[ERROR] Error processing file {path}: {e.__class__.__name__}: {e}")
        raise
