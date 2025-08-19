"""Command line interface for the forma toolkit."""

from __future__ import annotations

from pathlib import Path
from typing import List

import typer
from rich.console import Console

from .controller import run_conversion
from .types import Strategy

app = typer.Typer(
    name="forma",
    help="一个双引擎、智能的文档转换工具集。",
    add_completion=False,
)
console = Console()


@app.command()
def convert(
    inputs: List[Path] = typer.Argument(
        ...,
        help="输入文件或文件夹的路径。",
        exists=True,
    ),
    output_dir: Path = typer.Option(
        ...,
        "--output",
        "-o",
        help="用于保存输出文件的目录。",
        file_okay=False,
        dir_okay=True,
    ),
    strategy: Strategy = typer.Option(
        Strategy.AUTO,
        "--strategy",
        "-s",
        help="要使用的转换策略。",
        case_sensitive=False,
    ),
    recursive: bool = typer.Option(
        True, "--recursive/--no-recursive", help="递归处理目录。"
    ),
) -> None:
    """转换文档 (PDF, DOCX, 图片) 为 Markdown。

    默认使用 'auto' 策略:
    - 首先尝试快速的本地转换。
    - 如果结果质量较低 (例如，扫描版的PDF)，它将自动切换到
      强大的视觉语言模型进行深度分析。
    """
    console.print(f"[bold green]forma[/] | 开始转换...")
    console.print(f"- 使用策略: [cyan]{strategy.value}[/]")
    console.print(f"- 输出目录: [cyan]{output_dir}[/]")

    try:
        run_conversion(
            inputs=inputs, output_dir=output_dir, strategy=strategy, recursive=recursive
        )
        console.print("\n[bold green]✔ 转换完成.[/]")
    except Exception as e:
        console.print(f"\n[bold red]✖ 发生错误:[/]")
        console.print(f"[red]{e}[/]")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
