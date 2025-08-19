"""Command line interface for the forma toolkit."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import List

import typer
from rich.console import Console

console = Console()

app = typer.Typer()


class Strategy(str, Enum):
    """Execution strategy for conversion."""

    AUTO = "auto"
    FAST = "fast"
    DEEP = "deep"


@app.command()
def convert(
    inputs: List[Path] = typer.Argument(
        ..., help="一个或多个输入文件/文件夹路径",
    ),
    output_dir: Path = typer.Option(
        ..., "--output", "-o", help="统一的输出文件夹",
    ),
    strategy: Strategy = typer.Option(
        Strategy.AUTO, "--strategy", "-s", help="选择处理策略",
    ),
    recursive: bool = typer.Option(
        True, "--recursive/--no-recursive", help="是否递归处理文件夹",
    ),
) -> None:
    """智能转换文档 (PDF, DOCX, 图片) 为 Markdown。"""

    from .controller import run_conversion

    run_conversion(inputs, output_dir, strategy, recursive)


if __name__ == "__main__":  # pragma: no cover
    app()
