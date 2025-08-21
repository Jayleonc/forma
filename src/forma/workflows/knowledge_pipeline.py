"""Workflow module for knowledge base construction pipeline."""

from __future__ import annotations

import json
from pathlib import Path
import time
from typing import Dict, List

import pandas as pd
from rich.console import Console
from rich.panel import Panel

from ..core.chunker import MarkdownChunker
from ..core.knowledge_builder import KnowledgeBuilder
from ..core.models import Chunk, EnrichedChunk, AuthoritativeKnowledgeUnit

__all__ = ["run_knowledge_pipeline"]

console = Console()


def run_knowledge_pipeline(
    input_path: Path,
    output_dir: Path,
    export_csv: bool = False,
    output_name: str | None = None,
) -> None:
    """Run the three-stage knowledge building pipeline."""
    md_content = input_path.read_text(encoding="utf-8")

    # ------------------- Stage 1 -------------------
    t0 = time.perf_counter()

    console.rule("[bold cyan]Stage 1: Chunk Markdown[/bold cyan]", style="cyan")
    chunker = MarkdownChunker(source_filename=input_path.name)
    chunks = chunker.chunk(md_content)
    console.print(
        Panel(
            json.dumps([c.model_dump() for c in chunks], indent=2, ensure_ascii=False),
            title="[bold green]Chunks[/bold green]",
            border_style="green",
        )
    )
    console.print(f"[yellow]Stage 1 duration: {time.perf_counter() - t0:.2f}s[/]")

    # ------------------- Stage 2 -------------------
    t1 = time.perf_counter()

    console.rule("[bold cyan]Stage 2: Distil Local Knowledge[/bold cyan]", style="cyan")
    builder = KnowledgeBuilder()
    enriched_chunks: List[EnrichedChunk] = builder.distill_knowledge_in_batch(chunks)
    console.print(
        Panel(
            json.dumps([ec.model_dump() for ec in enriched_chunks], indent=2, ensure_ascii=False),
            title="[bold green]Enriched Chunks[/bold green]",
            border_style="green",
        )
    )
    console.print(f"[yellow]Stage 2 duration: {time.perf_counter() - t1:.2f}s[/]")

    # ------------------- Stage 3 -------------------
    t2 = time.perf_counter()

    console.rule(
        "[bold cyan]Stage 3: Synthesize Global Knowledge[/bold cyan]",
        style="cyan",
    )
    knowledge_units: List[AuthoritativeKnowledgeUnit] = builder._synthesize_global_knowledge(
        enriched_chunks
    )
    console.print(
        Panel(
            json.dumps([ku.model_dump() for ku in knowledge_units], indent=2, ensure_ascii=False),
            title="[bold green]Knowledge Units[/bold green]",
            border_style="green",
        )
    )
    console.print(f"[yellow]Stage 3 duration: {time.perf_counter() - t2:.2f}s[/]")

    output_dir.mkdir(parents=True, exist_ok=True)
    base_name = output_name or input_path.stem
    output_path = output_dir / f"{base_name}_knowledge_base.jsonl"
    with output_path.open("w", encoding="utf-8") as f:
        for unit in knowledge_units:
            f.write(json.dumps(unit.model_dump(), ensure_ascii=False) + "\n")
    console.print(
        f"\n[bold green]✔ Knowledge pipeline complete. Output saved to {output_path}[/bold green]"
    )

    if export_csv:
        csv_output_path = output_dir / f"{base_name}_knowledge_base.csv"
        csv_records: List[Dict[str, str]] = []
        with open(output_path, "r", encoding="utf-8") as f:
            for line in f:
                data = json.loads(line)
                category = data.get("category")
                for qa_pair in data.get("qa_pairs", []):
                    question = qa_pair.get("question")
                    answer = qa_pair.get("answer")
                    csv_records.append({
                        "question": question,
                        "answer": answer,
                        "category": category,
                    })
        df = pd.DataFrame(csv_records)
        df.to_csv(csv_output_path, index=False)
        console.print(
            f"✅  Successfully exported flattened knowledge to {csv_output_path}"
        )
