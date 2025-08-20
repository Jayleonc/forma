"""Core orchestration logic for document conversion."""

from __future__ import annotations

from pathlib import Path
from typing import List

from .types import Strategy
from .core.processors import (
    DocxProcessor,
    ImageProcessor,
    PdfProcessor,
    PptxProcessor,
    Processor,
    ProcessingResult,
)
from .core.vlm import VlmParser
from .config import get_vlm_config
from .core.qa_generator import QAGenerator

THRESHOLD = get_vlm_config().auto_threshold


class Controller:
    """Orchestrates higher level forma workflows."""

    def generate_qa_pipeline(self, input_path: Path, output_dir: Path) -> None:
        qa_generator = QAGenerator()
        md_content = input_path.read_text(encoding="utf-8")
        print("运行阶段一：生成原始问答对...")
        raw_qas = qa_generator.run_generation_stage(md_content)
        print("运行阶段二：生成全局分类体系...")
        questions = [qa["question"] for qa in raw_qas]
        categories = qa_generator.run_categorization_stage(questions)
        print("运行阶段三：合成问答并指派分类...")
        final_qas = qa_generator.run_synthesis_stage(raw_qas, categories)
        output_dir.mkdir(parents=True, exist_ok=True)
        import pandas as pd

        output_path = output_dir / f"{input_path.stem}_faq.csv"
        pd.DataFrame(final_qas).to_csv(output_path, index=False)

def run_conversion(
    inputs: List[Path],
    output_dir: Path,
    strategy: Strategy,
    recursive: bool,
    prompt_name: str = "default_image_description",
) -> None:
    """Entry point invoked by the CLI."""

    files = _discover_files(inputs, recursive)
    output_dir.mkdir(parents=True, exist_ok=True)
    vlm_parser = VlmParser() if strategy != Strategy.FAST else None
    for path in files:
        _process_single_file(path, output_dir, strategy, vlm_parser, prompt_name)


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


def _select_processor(path: Path) -> Processor | None:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return PdfProcessor()
    if suffix in {".png", ".jpg", ".jpeg", ".bmp"}:
        return ImageProcessor()
    if suffix == ".docx":
        return DocxProcessor()
    if suffix == ".pptx":
        return PptxProcessor()
    return None


def _process_single_file(
    path: Path,
    output_dir: Path,
    strategy: Strategy,
    vlm_parser: VlmParser | None = None,
    prompt_name: str = "default_image_description",
) -> None:
    processor = _select_processor(path)
    if processor is None:
        return

    output_path = output_dir / f"{path.stem}.md"

    if strategy == Strategy.DEEP:
        if not vlm_parser:
            vlm_parser = VlmParser()
        markdown = vlm_parser.parse(path, prompt_name=prompt_name)
        output_path.write_text(markdown, encoding="utf-8")
        return

    result: ProcessingResult = processor.process(path)
    final_md = result.markdown_content

    if strategy == Strategy.AUTO and (result.low_confidence or result.text_char_count < THRESHOLD):
        if not vlm_parser:
            vlm_parser = VlmParser()
        final_md = vlm_parser.parse(path, prompt_name=prompt_name)

    output_path.write_text(final_md, encoding="utf-8")


__all__ = ["run_conversion", "Controller"]
