"""
示例脚本：使用 forma 的 parse_pdf 功能将单个 PDF 转换为 Markdown。

用法示例：
    python examples/pdf_to_md.py input.pdf output.md
"""
from __future__ import annotations

import sys
from pathlib import Path

# 在本地仓库直接运行脚本时，将 src 目录加入搜索路径
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from forma.core.parser import parse_pdf  # noqa: E402  # 延后导入避免路径问题


def main() -> None:  # noqa: D401  不需要英文 docstring
    if len(sys.argv) != 3:
        print("用法: python pdf_to_md.py <输入 PDF 路径> <输出 Markdown 路径>")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])

    if not input_path.exists():
        print(f"❌ 输入文件不存在: {input_path}")
        sys.exit(1)

    markdown = parse_pdf(str(input_path))
    output_path.write_text(markdown, encoding="utf-8")
    print(f"✅ 已生成 Markdown: {output_path}")


if __name__ == "__main__":
    main()
