"""
示例脚本：批量将文件夹中的所有 PDF 转为 Markdown。

用法示例：
    python examples/batch_pdf_folder.py input_dir output_dir

- input_dir：包含若干 .pdf 文件的目录。
- output_dir：输出目录，不存在会自动创建，生成同名 .md 文件。
"""
from __future__ import annotations

import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from forma.core.parser import parse_pdf  # noqa: E402


def convert_single(pdf_path: Path, out_dir: Path) -> None:
    """将单个 PDF 转为 Markdown。"""
    md_path = out_dir / (pdf_path.stem + ".md")
    markdown = parse_pdf(str(pdf_path))
    md_path.write_text(markdown, encoding="utf-8")
    print(f"✔ {pdf_path.name} → {md_path.name}")


def main() -> None:
    if len(sys.argv) != 3:
        print("用法: python batch_pdf_folder.py <输入目录> <输出目录>")
        sys.exit(1)

    in_dir = Path(sys.argv[1])
    out_dir = Path(sys.argv[2])

    if not in_dir.is_dir():
        print(f"❌ 输入目录不存在: {in_dir}")
        sys.exit(1)

    out_dir.mkdir(parents=True, exist_ok=True)

    pdf_files = sorted(in_dir.glob("*.pdf"))
    if not pdf_files:
        print("⚠️ 输入目录内未找到 PDF 文件")
        sys.exit(0)

    # 使用线程池并行处理，提升 I/O 性能
    with ThreadPoolExecutor() as exec:
        futures = [exec.submit(convert_single, pdf, out_dir) for pdf in pdf_files]
        for _ in as_completed(futures):
            pass  # 进度打印在 convert_single 中

    print("✅ 全部处理完成！")


if __name__ == "__main__":
    main()
