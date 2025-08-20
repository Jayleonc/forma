"""Workflow module for FAQ QA generation pipeline.

Extracted from the original `Controller.generate_qa_pipeline` for single-responsibility.
Exposes `generate_qa_pipeline` which is consumed by the CLI.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from rich.console import Console
from rich.panel import Panel

from ..core.qa_generator import QAGenerator

__all__ = ["generate_qa_pipeline"]

console = Console()


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

    console.rule("[bold cyan]Stage 1: Generate Raw QAs[/bold cyan]", style="cyan")
    raw_qas = qa_generator.run_generation_stage(md_content)
    console.print(
        Panel(
            json.dumps(raw_qas, indent=2, ensure_ascii=False),
            title="[bold green]Raw QAs[/bold green]",
            border_style="green",
        )
    )

    if not raw_qas:
        console.print("[bold red]Error: Stage 1 produced no raw QAs. Aborting.[/bold red]")
        return

    console.rule("[bold cyan]Stage 2: Generate Categories[/bold cyan]", style="cyan")
    questions = [qa["question"] for qa in raw_qas]
    categories = qa_generator.run_categorization_stage(questions)
    console.print(
        Panel(
            json.dumps(categories, indent=2, ensure_ascii=False),
            title="[bold green]Categories[/bold green]",
            border_style="green",
        )
    )

    if not categories:
        console.print("[bold red]Error: Stage 2 produced no categories. Aborting.[/bold red]")
        return

    console.rule("[bold cyan]Stage 3: Synthesize Final QAs[/bold cyan]", style="cyan")
    final_qas = qa_generator.run_synthesis_stage(raw_qas, categories)
    console.print(
        Panel(
            json.dumps(final_qas, indent=2, ensure_ascii=False),
            title="[bold green]Final QAs[/bold green]",
            border_style="green",
        )
    )

    if not final_qas:
        console.print("[bold red]Error: Stage 3 produced no final QAs. CSV will be empty.[/bold red]")

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{input_path.stem}_faq.csv"
    pd.DataFrame(final_qas).to_csv(output_path, index=False)
    console.print(f"\n[bold green]✔ QA pipeline complete. Output saved to {output_path}[/bold green]")
