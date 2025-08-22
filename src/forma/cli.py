"""Command line interface for the forma toolkit."""

from __future__ import annotations

from pathlib import Path
from typing import List
import json
from concurrent.futures import ProcessPoolExecutor, as_completed

import pandas as pd
import typer
from rich.console import Console, Group
from rich.live import Live
from rich.progress import (
    BarColumn,
    Progress,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

from .workflows.conversion import run_conversion
from .custom_types import Strategy

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
    prompt_name: str = typer.Option(
        "default_image_description",
        "--prompt",
        "-p",
        help="要使用的 VLM Prompt 名称。",
    ),
    output_name: str = typer.Option(
        None,
        "--output-name",
        "-n",
        help="输出文件的名称（不含扩展名）。如果处理多个文件，此选项将被忽略。",
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
            inputs=inputs,
            output_dir=output_dir,
            strategy=strategy,
            recursive=recursive,
            prompt_name=prompt_name,
            output_name=output_name,
        )
        console.print("\n[bold green]✔ 转换完成.[/]")
    except Exception as e:
        console.print(f"\n[bold red]✖ 发生错误:[/]")
        console.print(f"[red]{e}[/]")
        raise typer.Exit(code=1)


@app.command(
    "qa", help="从 Markdown 文档构建分层的 RAG 知识库 (.jsonl)。"
)
def generate_qa(
    input_path: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
        help="输入的 Markdown 文件路径。",
    ),
    output_dir: Path = typer.Option(
        ...,
        "-o",
        "--output",
        help="用于保存输出 JSONL 文件的目录。",
        file_okay=False,
        dir_okay=True,
        writable=True,
        resolve_path=True,
    ),
    name: str | None = typer.Option(
        None,
        "-n",
        "--name",
        help="输出文件的基准名称（不包含扩展名）。若未提供，则使用输入文件名。",
    ),
    export_csv: bool = typer.Option(
        False,
        "--export-csv",
        help="Additionally export a flattened CSV file (question, answer, category).",
        show_default=False,
    ),
) -> None:
    """从Markdown文档构建分层的知识库并保存为JSONL文件。"""

    from forma.workflows.knowledge_pipeline import run_knowledge_pipeline

    run_knowledge_pipeline(input_path, output_dir, export_csv=export_csv, output_name=name)
    console.print(f"✅ 知识库构建完成，结果已保存至 {output_dir}")


def _process_single_file(input_path: Path, output_dir: Path) -> tuple[str, int, Path]:
    """Worker helper to build knowledge for a single markdown file."""
    from forma.workflows.knowledge_pipeline import run_knowledge_pipeline

    run_knowledge_pipeline(input_path, output_dir, export_csv=False)
    output_path = output_dir / f"{input_path.stem}_knowledge_base.jsonl"
    qa_count = 0
    with output_path.open("r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            try:
                data = json.loads(s)
            except json.JSONDecodeError:
                console.print(f"[yellow]警告[/]: 跳过无法解析的 JSONL 行: {s[:80]}")
                continue
            qa_count += len(data.get("qa_pairs", []))
    return input_path.name, qa_count, output_path


@app.command("knowledge-base", help="批量处理 Markdown 文档构建知识库。")
@app.command("kb", hidden=True)
def build_knowledge_base(
    input_dir: Path = typer.Argument(
        ..., exists=True, file_okay=False, dir_okay=True, readable=True
    ),
    output_dir: Path = typer.Option(
        ..., "-o", "--output", file_okay=False, dir_okay=True, writable=True
    ),
    export_csv: bool = typer.Option(
        False,
        "--export-csv",
        help="处理完成后导出聚合的 CSV 文件。",
        show_default=False,
    ),
    recursive: bool = typer.Option(
        True,
        "--recursive/--no-recursive",
        help="是否递归查找子目录中的 Markdown 文件。",
    ),
) -> None:
    """Process a directory of Markdown files concurrently."""

    md_files = list(input_dir.rglob("*.md") if recursive else input_dir.glob("*.md"))
    if not md_files:
        console.print("[bold red]未找到任何 Markdown 文件。[/]")
        raise typer.Exit(code=1)

    statuses = {p: f"[cyan]IN PROGRESS[/cyan] 📄 {p.name}" for p in md_files}
    progress = Progress(
        TextColumn("{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
    )
    overall_task = progress.add_task("总体进度", total=len(md_files))

    def render() -> Group:
        table = Table(show_header=False)
        for p in md_files:
            table.add_row(statuses[p])
        return Group(progress, table)

    success, failure, total_qa = 0, 0, 0
    results: list[tuple[Path, Path]] = []

    with Live(render(), refresh_per_second=5, console=console) as live:
        with ProcessPoolExecutor() as executor:
            future_map = {
                executor.submit(_process_single_file, path, output_dir): path
                for path in md_files
            }
            for future in as_completed(future_map):
                path = future_map[future]
                try:
                    name, qa_count, out_path = future.result()
                    statuses[path] = (
                        f"[bold green]✔ DONE[/bold green]      📄 {name} (生成了 {qa_count} 条QA)"
                    )
                    success += 1
                    total_qa += qa_count
                    results.append((path, out_path))
                except Exception as e:  # noqa: BLE001
                    statuses[path] = (
                        f"[bold red]✖ FAILED[/bold red]     📄 {path.name} (错误: {e})"
                    )
                    failure += 1
                progress.advance(overall_task)
                live.update(render())

    if export_csv:
        csv_output = output_dir / "knowledge_base.csv"
        records = []
        for src_path, jsonl_path in results:
            with jsonl_path.open("r", encoding="utf-8") as f:
                for line in f:
                    s = line.strip()
                    if not s:
                        continue
                    try:
                        data = json.loads(s)
                    except json.JSONDecodeError:
                        console.print(
                            f"[yellow]警告[/]: 跳过无法解析的 JSONL 行 (文件: {jsonl_path.name}): {s[:80]}"
                        )
                        continue
                    category = data.get("category")
                    for qa in data.get("qa_pairs", []):
                        records.append(
                            {
                                "question": qa.get("question"),
                                "answer": qa.get("answer"),
                                "category": category,
                                "source_file": src_path.name,
                            }
                        )
        if records:
            df = pd.DataFrame(records)
            df.to_csv(csv_output, index=False)

    console.print("\n[bold green]✔ 知识库构建完成！[/]")
    console.print(f"- 成功处理: {success} 个文件")
    console.print(f"- 失败: {failure} 个文件")
    console.print(f"- 总计生成: {total_qa} 条知识记录")
    console.print(f"- 输出目录: {output_dir}")
    if export_csv:
        console.print(f"- 聚合 CSV 文件: {output_dir / 'knowledge_base.csv'}")


if __name__ == "__main__":
    app()
