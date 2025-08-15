"""Command line interface for the forma toolkit."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from .core.parser import parse_pdf
from .core.ocr import ocr_image_file

console = Console()

app = typer.Typer()


@app.command()
def pdf(
    input: Path = typer.Option(
        ..., exists=True, file_okay=True, dir_okay=False, help="Path to the input PDF"
    ),
    output: Path = typer.Option(
        ..., file_okay=True, dir_okay=False, help="Where to write the output Markdown"
    ),
) -> None:
    """Parse a PDF and write the resulting Markdown."""
    markdown = parse_pdf(str(input))
    output.write_text(markdown, encoding="utf-8")
    console.print(
        f"✔ Parsed [cyan]{input}[/] to [cyan]{output}[/]", style="green"
    )


@app.command()
def image(
    input: Path = typer.Option(
        ..., exists=True, file_okay=True, dir_okay=False, help="Path to the input image"
    ),
    output: Path = typer.Option(
        ..., file_okay=True, dir_okay=False, help="Where to write the OCR text"
    ),
) -> None:
    """Run OCR on a single image and write the text output."""
    text = ocr_image_file(str(input))
    output.write_text(text, encoding="utf-8")
    console.print(
        f"✔ OCR processed [cyan]{input}[/] to [cyan]{output}[/]", style="green"
    )


if __name__ == "__main__":  # pragma: no cover
    app()

