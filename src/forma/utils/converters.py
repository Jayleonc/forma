"""Utilities for file format conversions."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import fitz  # PyMuPDF


def convert_ppt_slide_to_image(
    ppt_path: Path, slide_index: int, output_dir: Path
) -> Path:
    """
    将PPTX文件的特定幻灯片转换为PNG图像。

    这个函数通过两个步骤完成转换：
    1. PPTX -> PDF (使用 LibreOffice 的 headless 模式)
    2. PDF page -> PNG (使用 PyMuPDF)

    Args:
        ppt_path: PPTX文件的绝对路径。
        slide_index: 要转换的幻灯片的0-based索引。
        output_dir: 最终图像保存的目录。

    Returns:
        生成的PNG图像的路径。

    Raises:
        RuntimeError: 如果 LibreOffice 未找到或失败，或者中间 PDF 未创建。
        ValueError: 如果 slide_index 超出范围。
    """
    with tempfile.TemporaryDirectory() as tmp_pdf_dir_str:
        tmp_pdf_dir = Path(tmp_pdf_dir_str)

        # Step 1: Convert PPTX to PDF using LibreOffice
        try:
            cmd = [
                "libreoffice",
                "--headless",
                "--convert-to",
                "pdf",
                "--outdir",
                str(tmp_pdf_dir),
                str(ppt_path),
            ]
            subprocess.run(
                cmd, check=True, capture_output=True, text=True, timeout=120
            )
        except (
            subprocess.CalledProcessError, 
            FileNotFoundError, 
            subprocess.TimeoutExpired
        ) as e:
            error_message = (
                "PPTX to PDF conversion failed. Please ensure LibreOffice is installed "
                f"and accessible in the system's PATH. Error: {e}"
            )
            raise RuntimeError(error_message) from e

        pdf_path = tmp_pdf_dir / f"{ppt_path.stem}.pdf"
        if not pdf_path.exists():
            raise RuntimeError(f"Conversion failed: PDF file not found at {pdf_path}")

        # Step 2: Extract the specific page as an image using PyMuPDF
        doc = fitz.open(str(pdf_path))
        if not (0 <= slide_index < len(doc)):
            doc.close()
            raise ValueError(
                f"Slide index {slide_index} is out of bounds for document "
                f"with {len(doc)} pages."
            )

        page = doc.load_page(slide_index)
        pix = page.get_pixmap(dpi=200)  # Higher DPI for better quality
        output_image_path = output_dir / f"complex_slide_{slide_index}.png"
        pix.save(str(output_image_path))
        doc.close()

    return output_image_path
