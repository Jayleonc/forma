"""Knowledge pipeline for building QA datasets from Markdown.

This module was recreated to restore functionality after the `workflows`
directory was removed during refactoring.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd
from rich.console import Console
from rich.panel import Panel

from ..shared.chunker import HierarchicalChunker
from .builder import KnowledgeBuilder


def run_knowledge_pipeline(
    input_path: Path,
    output_dir: Path,
    export_csv: bool = False,
    output_name: str | None = None,
) -> None:
    """Runs the full knowledge base generation pipeline for a single document."""
    console = Console()
    output_dir.mkdir(parents=True, exist_ok=True)
    start_time = time.time()
    last_stage_time = start_time

    # Stage 1: Reading content
    console.print(Panel("Stage 1/4: Reading content", title="[bold cyan]Pipeline Status[/bold cyan]", expand=False))
    content = input_path.read_text(encoding="utf-8")
    current_time = time.time()
    console.print(f"  -> Done in {current_time - last_stage_time:.2f}s\n")
    last_stage_time = current_time

    # Stage 2: Chunking content
    console.print(Panel("Stage 2/4: Chunking content", title="[bold cyan]Pipeline Status[/bold cyan]", expand=False))
    chunker = HierarchicalChunker(source_filename=str(input_path))
    chunks = chunker.chunk(content)
    console.print(f"  -> Found {len(chunks)} chunks.")
    # Persist chunks for inspection
    base_name = output_name or input_path.stem
    chunks_path = output_dir / f"{base_name}_chunks.jsonl"
    try:
        with chunks_path.open("w", encoding="utf-8") as f:
            for ch in chunks:
                f.write(
                    json.dumps(
                        {
                            "chunk_id": ch.chunk_id,
                            "text": ch.text,
                            "metadata": ch.metadata,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        console.print(f"  -> Chunks saved to: {chunks_path}")
    except Exception as e:
        console.print(f"  -> [red]Failed to save chunks[/red]: {e}")
    current_time = time.time()
    console.print(f"  -> Done in {current_time - last_stage_time:.2f}s\n")
    last_stage_time = current_time

    # Stage 3: Building knowledge
    console.print(Panel("Stage 3/4: Building knowledge", title="[bold cyan]Pipeline Status[/bold cyan]", expand=False))
    builder = KnowledgeBuilder()
    enriched_chunks = builder.distill_knowledge_in_batch(chunks)
    authoritative_knowledge = builder._synthesize_global_knowledge(enriched_chunks)
    console.print(f"  -> Built {len(authoritative_knowledge)} authoritative knowledge units.")
    current_time = time.time()
    console.print(f"  -> Done in {current_time - last_stage_time:.2f}s\n")
    last_stage_time = current_time

    # Stage 4: Saving results
    console.print(Panel("Stage 4/4: Saving results", title="[bold cyan]Pipeline Status[/bold cyan]", expand=False))
    base_name = output_name or input_path.stem
    output_path = output_dir / f"{base_name}_knowledge_base.jsonl"

    with output_path.open("w", encoding="utf-8") as f:
        for unit in authoritative_knowledge:
            f.write(json.dumps(unit.model_dump(), ensure_ascii=False) + "\n")

    if export_csv:
        records = []
        for unit in authoritative_knowledge:
            category = unit.category
            for qa in unit.qa_pairs:
                records.append(
                    {
                        "question": qa["question"],
                        "answer": qa["answer"],
                        "category": category,
                    }
                )
        if records:
            df = pd.DataFrame(records)
            csv_path = output_dir / f"{base_name}_knowledge_base.csv"
            df.to_csv(csv_path, index=False)

__all__ = ["run_knowledge_pipeline"]
