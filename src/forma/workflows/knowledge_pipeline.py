"""Workflow module for knowledge base construction pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List

from rich.console import Console
from rich.panel import Panel

from ..core.chunker import MarkdownChunker
from ..core.knowledge_builder import KnowledgeBuilder
from ..core.models import Chunk, EnrichedChunk, AuthoritativeKnowledgeUnit

__all__ = ["run_knowledge_pipeline"]

console = Console()


def run_knowledge_pipeline(input_path: Path, output_dir: Path) -> None:
    """Run the four-stage knowledge building pipeline."""
    md_content = input_path.read_text(encoding="utf-8")

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

    console.rule("[bold cyan]Stage 2: Distil Local Knowledge[/bold cyan]", style="cyan")
    builder = KnowledgeBuilder()
    enriched_chunks: List[EnrichedChunk] = []
    with ThreadPoolExecutor() as executor:
        future_map = {
            executor.submit(builder._distill_knowledge_from_chunk, ch): ch.chunk_id
            for ch in chunks
        }
        for future in as_completed(future_map):
            enriched_chunks.append(future.result())
    console.print(
        Panel(
            json.dumps([ec.model_dump() for ec in enriched_chunks], indent=2, ensure_ascii=False),
            title="[bold green]Enriched Chunks[/bold green]",
            border_style="green",
        )
    )

    console.rule("[bold cyan]Stage 3: Discover Themes[/bold cyan]", style="cyan")
    themes = builder._discover_global_themes(enriched_chunks)
    console.print(
        Panel(
            json.dumps(themes, indent=2, ensure_ascii=False),
            title="[bold green]Themes[/bold green]",
            border_style="green",
        )
    )

    theme_to_chunks: Dict[str, List[EnrichedChunk]] = {}
    for item in themes:
        theme = item.get("theme")
        chunk_ids = item.get("chunk_ids", [])
        related = [ec for ec in enriched_chunks if ec.chunk_id in chunk_ids]
        if theme:
            theme_to_chunks[theme] = related

    console.rule("[bold cyan]Stage 4: Fuse Knowledge by Theme[/bold cyan]", style="cyan")
    knowledge_units: List[AuthoritativeKnowledgeUnit] = []
    for theme, related in theme_to_chunks.items():
        knowledge_units.append(builder._fuse_knowledge_by_theme(theme, related))
    console.print(
        Panel(
            json.dumps([ku.model_dump() for ku in knowledge_units], indent=2, ensure_ascii=False),
            title="[bold green]Knowledge Units[/bold green]",
            border_style="green",
        )
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{input_path.stem}_knowledge_base.jsonl"
    with output_path.open("w", encoding="utf-8") as f:
        for unit in knowledge_units:
            f.write(json.dumps(unit.model_dump(), ensure_ascii=False) + "\n")
    console.print(
        f"\n[bold green]✔ Knowledge pipeline complete. Output saved to {output_path}[/bold green]"
    )
