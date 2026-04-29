"""Workflow module for document conversion.

This was extracted from the previous `controller.py` to separate concerns.
Exposes a single public helper `run_conversion` used by the CLI.
"""

from __future__ import annotations
import logging
from pathlib import Path
from typing import List

# 移除 pebble 和 concurrent.futures 导入，使用 asyncio 统一并发模型
from ..vision import OpenAIVLMClient, VlmParser, VLMClient
from ..shared.custom_types import Strategy
from .processors import (
    DocxProcessor,
    ImageProcessor,
    PdfProcessor,
    PptxProcessor,
    TextProcessor,
    XlsxProcessor,
    Processor,
    ProcessingResult,
)
from ..shared.utils.markdown_cleaner import MarkdownCleaner
from ..shared.config import get_vlm_config


logger = logging.getLogger(__name__)

THRESHOLD = get_vlm_config().auto_threshold

__all__ = ["convert_path", "run_conversion", "process_fallback", "run_fallback", "VLM_SUPPORTED_SUFFIXES"]


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
) -> List[ProcessingResult]:
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

    results: List[ProcessingResult] = []
    for path in files:
        result = convert_path(
            path,
            strategy,
            vlm_parser=vlm_parser,
            vlm_client=vlm_client,
            prompt_name=prompt_name,
            use_ocr_for_images=use_ocr_for_images,
        )
        stem = effective_output_name if effective_output_name else path.stem
        output_path = output_dir / f"{stem}.md"
        logger.debug(
            "Writing converted markdown to %s, content length: %s",
            output_path,
            len(result.markdown_content),
        )
        output_path.write_text(result.markdown_content, encoding="utf-8")
        results.append(result)
    return results


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
    logger.debug("Selecting processor for file: %s, suffix: %s", path, suffix)

    # 基于文件后缀名选择处理器
    if suffix == ".pdf":
        logger.debug(
            "Selected PdfProcessor for %s based on suffix, use_ocr=%s",
            path,
            use_ocr_for_images,
        )
        return PdfProcessor(vlm_client=vlm_client, use_ocr=use_ocr_for_images)
    if suffix in {".png", ".jpg", ".jpeg", ".bmp"}:
        logger.debug("Selected ImageProcessor for %s based on suffix", path)
        return ImageProcessor()
    if suffix == ".docx":
        logger.debug("Selected DocxProcessor for %s based on suffix", path)
        return DocxProcessor(vlm_client=vlm_client)
    if suffix == ".pptx":
        logger.debug("Selected PptxProcessor for %s based on suffix", path)
        return PptxProcessor(vlm_client=vlm_client)
    if suffix in {".xlsx", ".xls"}:
        logger.debug("Selected XlsxProcessor for %s based on suffix", path)
        return XlsxProcessor()
    if suffix in {".md", ".markdown", ".txt"}:
        logger.debug("Selected TextProcessor for %s based on suffix", path)
        return TextProcessor()

    # 如果没有后缀名或后缀名不匹配，尝试基于文件内容检测类型
    logger.info("Attempting to detect file type based on content for: %s", path)
    try:
        # 读取文件头部字节用于检测文件类型
        with open(path, 'rb') as f:
            header = f.read(8)  # 读取前8个字节

        # PDF文件头部特征: %PDF
        if header.startswith(b'%PDF'):
            logger.debug(
                "Detected PDF file based on content signature for %s", path
            )
            return PdfProcessor()

        # Office文件头部特征: PK (ZIP格式) — 需要进一步区分 docx/pptx/xlsx
        elif header.startswith(b'PK'):
            import zipfile
            try:
                with zipfile.ZipFile(path, 'r') as zf:
                    names = zf.namelist()
                    if any(n.startswith('xl/') for n in names):
                        logger.debug("Detected XLSX based on ZIP contents for %s", path)
                        return XlsxProcessor()
                    elif any(n.startswith('ppt/') for n in names):
                        logger.debug("Detected PPTX based on ZIP contents for %s", path)
                        return PptxProcessor(vlm_client=vlm_client)
                    else:
                        logger.debug("Detected DOCX (default) based on ZIP contents for %s", path)
                        return DocxProcessor(vlm_client=vlm_client)
            except zipfile.BadZipFile:
                logger.warning("File %s has PK header but is not a valid ZIP", path)
                return None

        # 图像文件头部特征
        elif header.startswith(b'\xff\xd8'):  # JPEG
            logger.debug(
                "Detected JPEG image based on content signature for %s", path
            )
            return ImageProcessor()
        elif header.startswith(b'\x89PNG'):  # PNG
            logger.debug(
                "Detected PNG image based on content signature for %s", path
            )
            return ImageProcessor()
        elif header.startswith(b'GIF8'):  # GIF
            logger.debug(
                "Detected GIF image based on content signature for %s", path
            )
            return ImageProcessor()
        elif header.startswith(b'BM'):  # BMP
            logger.debug(
                "Detected BMP image based on content signature for %s", path
            )
            return ImageProcessor()

    except Exception as e:
        logger.error(
            "Error during file type detection: %s: %s", e.__class__.__name__, e
        )

    logger.warning(
        "No processor found for file: %s with suffix: %s", path, suffix
    )
    return None


def convert_path(
    path: Path,
    strategy: Strategy,
    vlm_parser: VlmParser | None = None,
    vlm_client: VLMClient | None = None,
    prompt_name: str = "default_image_description",
    use_ocr_for_images: bool = False,
) -> ProcessingResult:
    logger.debug(
        "Processing file: %s, strategy: %s, use_ocr_for_images: %s",
        path,
        strategy,
        use_ocr_for_images,
    )
    processor = _select_processor(path, vlm_client, use_ocr_for_images)
    if processor is None:
        logger.error("No suitable processor found for %s, skipping file", path)
        return

    logger.debug("Using processor: %s", processor.__class__.__name__)
    # 图片文件统一由处理器内部根据策略决定使用 VLM 还是 OCR，
    # workflow 只做业务聚合（清洗与落盘）。
    if isinstance(processor, ImageProcessor):
        logger.debug("ImageProcessor will decide path by strategy: %s", strategy)
        # 对于 AUTO/DEEP，若未提供 vlm_parser，这里创建一个以便传入处理器
        if strategy in (Strategy.AUTO, Strategy.DEEP) and not vlm_parser:
            logger.debug(
                "Creating VlmParser for image processing (strategy=%s)", strategy
            )
            vlm_parser = VlmParser(vlm_client)
        markdown = processor.process_with_strategy(
            path, strategy, vlm_parser, prompt_name=prompt_name
        )
        cleaned_markdown = MarkdownCleaner.clean_markdown(markdown)
        return ProcessingResult(
            markdown_content=cleaned_markdown,
            text_char_count=len(cleaned_markdown),
            image_count=1,
            low_confidence=len(cleaned_markdown.strip()) == 0,
        )

    # TODO 这里可以优化，非图片的DEEP，直接走VLM，是不是不对呢。。。。
    if strategy == Strategy.DEEP:
        logger.debug("Using DEEP strategy for %s", path)
        if not vlm_parser:
            logger.debug("Creating VlmParser for deep processing")
            vlm_parser = VlmParser(vlm_client)
        logger.debug("Parsing file with VLM: %s", path)
        # 非图片类型在 DEEP 策略下走通用 VLM 解析
        markdown = vlm_parser.parse(path, prompt_name=prompt_name)
        # 应用Markdown清洗
        cleaned_markdown = MarkdownCleaner.clean_markdown(markdown)
        return ProcessingResult(
            markdown_content=cleaned_markdown,
            text_char_count=len(cleaned_markdown),
            image_count=0,
            low_confidence=len(cleaned_markdown.strip()) == 0,
        )

    logger.debug(
        "Using standard processor for %s: %s", path, processor.__class__.__name__
    )
    try:
        result = None
        final_md = None

        logger.debug(
            ">>> STEP 1: About to call processor.process() for %s", path
        )
        # 直接调用处理器的 process 方法，不再使用 pebble 线程池
        # 超时控制将在 server.py 中通过 asyncio.wait_for 实现
        result = processor.process(path)
        final_md = result.markdown_content
        logger.debug(
            "<<< STEP 1: processor.process() completed successfully. Result text length: %s",
            len(final_md),
        )
        
        # 注意：超时处理逻辑已移至 server.py 中的 asyncio.wait_for
        # 这里保留备用处理逻辑，供 server.py 中超时后调用
        
        # 超时处理逻辑已移至模块级函数 process_fallback

        # For AUTO mode on other file types, use confidence score to decide.
        if result and strategy == Strategy.AUTO and (
            result.low_confidence or result.text_char_count < THRESHOLD
        ):
            logger.debug(
                ">>> STEP 2: Entering AUTO mode fallback logic."
            )
            logger.debug(
                "Low confidence or text below threshold (%s < %s), using VLM",
                result.text_char_count,
                THRESHOLD,
            )
            if not vlm_parser:
                logger.debug("Creating VlmParser for fallback processing")
                vlm_parser = VlmParser(vlm_client)
            logger.debug("Parsing with VLM as fallback: %s", path)
            final_md = vlm_parser.parse(path, prompt_name=prompt_name)
            logger.debug("<<< STEP 2: AUTO mode fallback logic completed.")

        logger.debug(
            ">>> STEP 3: About to clean final markdown content (length: %s).",
            len(final_md),
        )
        # 应用Markdown清洗
        cleaned_final_md = MarkdownCleaner.clean_markdown(final_md)
        logger.debug(
            "<<< STEP 3: Markdown cleaning completed. Cleaned length: %s",
            len(cleaned_final_md),
        )
        result.markdown_content = cleaned_final_md
        result.text_char_count = len(cleaned_final_md)
        return result
    except Exception as e:
        logger.error(
            "Error processing file %s: %s: %s", path, e.__class__.__name__, e
        )
        raise


def process_fallback(processor, path, vlm_client, vlm_parser, prompt_name):
    """当主处理方法超时时的备用处理逻辑
    
    Parameters
    ----------
    processor : Processor
        文件处理器实例
    path : Path
        要处理的文件路径
    vlm_client : VLMClient | None
        VLM客户端实例
    vlm_parser : VlmParser | None
        VLM解析器实例
    prompt_name : str
        提示词名称
        
    Returns
    -------
    tuple
        (markdown_content, result)元组
    """
    if isinstance(processor, PdfProcessor) and hasattr(processor, "_use_ocr"):
        # 对于PDF处理器，可以切换到仅使用OCR模式
        logger.debug("Retrying with OCR-only mode for PDF")
        processor._use_ocr = True
        result = processor.process(path)
        return result.markdown_content, result
    else:
        # 对于其他处理器，如果有VLM可用，直接使用VLM
        if vlm_client:
            logger.debug("Falling back to VLM due to timeout")
            if not vlm_parser:
                vlm_parser = VlmParser(vlm_client)
            final_md = vlm_parser.parse(path, prompt_name=prompt_name)
            # 创建一个虚拟result对象
            result = ProcessingResult(
                markdown_content=final_md,
                text_char_count=len(final_md),
                image_count=0,
                low_confidence=False
            )
            return final_md, result
        else:
            raise RuntimeError("处理超时，且没有可用的备选方案")



# VlmParser.parse() only supports PDF and image files.
VLM_SUPPORTED_SUFFIXES = frozenset({".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".gif"})


def run_fallback(
    path: Path,
    prompt_name: str = "default_image_description",
) -> tuple:
    """Process-safe fallback entrypoint used by server.py."""
    suffix = path.suffix.lower()
    if suffix not in VLM_SUPPORTED_SUFFIXES:
        raise RuntimeError(
            f"文件类型 '{suffix}' 不支持 VLM fallback 处理，"
            f"仅支持: {sorted(VLM_SUPPORTED_SUFFIXES)}"
        )

    vlm_client = OpenAIVLMClient()
    vlm_parser = VlmParser(vlm_client)
    processor = _select_processor(path, vlm_client)
    if processor is None:
        raise RuntimeError(f"No suitable processor found for {path}")

    md, result = process_fallback(
        processor=processor,
        path=path,
        vlm_client=vlm_client,
        vlm_parser=vlm_parser,
        prompt_name=prompt_name,
    )

    text_char_count = result.text_char_count if result else len(md)
    low_confidence = result.low_confidence if result else (text_char_count < THRESHOLD)
    return md, text_char_count, low_confidence
