from __future__ import annotations

from pathlib import Path
import importlib
from typing import Any

from .core.parser import parse_text_pdf
from .core.ocr import parse_scanned_pdf

# Dynamically import typer to avoid mandatory dependency at test time
try:
    typer: Any = importlib.import_module("typer")
except Exception as exc:  # pragma: no cover - depends on external package
    raise RuntimeError("typer is required for the CLI") from exc

app = typer.Typer()


@app.command()
def parse(
    input_path: Path = typer.Option(
        ..., exists=True, file_okay=True, dir_okay=False, help="Path to the input PDF"
    ),
    output_path: Path = typer.Option(
        ..., file_okay=True, dir_okay=False, help="Where to write the output Markdown"
    ),
) -> None:
    """Parse a PDF into Markdown, choosing OCR for scanned files."""
    fitz: Any = importlib.import_module("fitz")
    doc = fitz.open(str(input_path))
    text_chars = sum(len(page.get_text()) for page in doc)

    if text_chars >= 100:
        markdown = parse_text_pdf(str(input_path))
    else:
        markdown = parse_scanned_pdf(str(input_path))

    output_path.write_text(markdown, encoding="utf-8")
    print(f"Parsing {input_path} to {output_path} completed.")


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    app()
