"""Example: batch convert all PDFs in a folder to Markdown using forma.

Run:
    python examples/process_folder.py /path/to/pdf_dir /path/to/output_dir

Each PDF found in the input directory will be converted to a Markdown file of
 the same stem inside the output directory using the library's intelligent
 routing (text vs scanned).
"""

from __future__ import annotations

import sys
from pathlib import Path

# Reuse the CLI's parse() logic directly
from forma.cli import parse as _parse_pdf  # type: ignore  # noqa: WPS433


def convert_folder(input_dir: Path, output_dir: Path) -> None:
    """Convert every PDF in *input_dir* to Markdown files in *output_dir*."""
    if not input_dir.is_dir():
        raise NotADirectoryError(f"Input directory not found: {input_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)

    for pdf_path in sorted(input_dir.glob("*.pdf")):
        md_path = output_dir / (pdf_path.stem + ".md")
        print(f"Converting {pdf_path} -> {md_path}")
        # type: ignore[arg-type]
        _parse_pdf(input_path=pdf_path, output_path=md_path)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python process_folder.py <input_dir> <output_dir>")
        sys.exit(1)

    in_dir = Path(sys.argv[1])
    out_dir = Path(sys.argv[2])
    convert_folder(in_dir, out_dir)
