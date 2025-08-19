"""
示例脚本：使用 forma OCR 引擎将单张图片转换为 Markdown。

用法示例：
    python examples/image_to_md.py input.png output.md
"""
from __future__ import annotations

import sys
from pathlib import Path

# 添加 src 到模块搜索路径，便于仓库根目录直接运行
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from forma.core.ocr import parse_image_to_markdown  # noqa: E402  延迟导入


def main() -> None:
    if len(sys.argv) != 3:
        print("用法: python image_to_md.py <输入图片路径> <输出 Markdown 路径>")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])

    if not input_path.exists():
        print(f"❌ 输入文件不存在: {input_path}")
        sys.exit(1)

    markdown = parse_image_to_markdown(str(input_path))
    output_path.write_text(markdown, encoding="utf-8")
    print(f"✅ 已生成 Markdown: {output_path}")


if __name__ == "__main__":
    main()
