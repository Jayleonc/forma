"""Utilities for file format conversions."""

from __future__ import annotations

import platform
import shutil
import subprocess
import tempfile
from pathlib import Path

import fitz  # PyMuPDF


def _find_libreoffice_path() -> str | None:
    """Finds the path to the LibreOffice executable."""
    # On macOS, check the default application path first
    if platform.system() == "Darwin":
        mac_path = "/Applications/LibreOffice.app/Contents/MacOS/soffice"
        if Path(mac_path).exists():
            return mac_path

    # For other systems or if not in the default Mac location, check PATH
    for cmd in ["libreoffice", "soffice"]:
        path = shutil.which(cmd)
        if path:
            return path

    return None



def convert_to_pdf(input_path: Path, output_dir: Path) -> Path:
    """
    使用 LibreOffice 将文档转换为 PDF。

    Args:
        input_path: 输入文件的绝对路径。
        output_dir: 保存生成的 PDF 的目录。

    Returns:
        生成的 PDF 文件的路径。

    Raises:
        RuntimeError: 如果 LibreOffice 未找到或转换失败。
    """
    libreoffice_path = _find_libreoffice_path()
    if not libreoffice_path:
        raise RuntimeError(
            "LibreOffice not found. Please install it and ensure it's in the system's PATH."
        )

    try:
        cmd = [
            libreoffice_path,
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(output_dir),
            str(input_path),
        ]
        subprocess.run(
            cmd, check=True, capture_output=True, text=True, timeout=120
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        error_message = (
            f"Document to PDF conversion failed using LibreOffice. Error: {e.stderr or e}"
        )
        raise RuntimeError(error_message) from e

    expected_pdf_path = output_dir / f"{input_path.stem}.pdf"
    if not expected_pdf_path.exists():
        raise RuntimeError(
            f"Conversion failed: PDF file not found at {expected_pdf_path}"
        )

    return expected_pdf_path
