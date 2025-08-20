"""Workflow module for FAQ QA generation pipeline.

Extracted from the original `Controller.generate_qa_pipeline` for single-responsibility.
Exposes `generate_qa_pipeline` which is consumed by the CLI.
"""

from __future__ import annotations

from pathlib import Path
import pandas as pd

from ..core.qa_generator import QAGenerator

__all__ = ["generate_qa_pipeline"]


def generate_qa_pipeline(input_path: Path, output_dir: Path) -> None:
    """Run the three-stage QA generation pipeline.

    Parameters
    ----------
    input_path: Path
        Markdown file to read.
    output_dir: Path
        Directory to write the resulting CSV file.
    """

    qa_generator = QAGenerator()
    md_content = input_path.read_text(encoding="utf-8")

    print("运行阶段一：生成原始问答对…")
    raw_qas = qa_generator.run_generation_stage(md_content)

    print("运行阶段二：生成全局分类体系…")
    questions = [qa["question"] for qa in raw_qas]
    categories = qa_generator.run_categorization_stage(questions)

    print("运行阶段三：合成问答并指派分类…")
    final_qas = qa_generator.run_synthesis_stage(raw_qas, categories)

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{input_path.stem}_faq.csv"
    pd.DataFrame(final_qas).to_csv(output_path, index=False)
