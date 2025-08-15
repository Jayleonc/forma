from __future__ import annotations

import sys
import types
from pathlib import Path

import fitz
from PIL import Image, ImageDraw

from forma.core import parser


def _create_text_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "hello text")
    doc.save(path)
    doc.close()


def _create_pdf_with_image(path: Path, with_text: bool) -> None:
    doc = fitz.open()
    page = doc.new_page()
    if with_text:
        page.insert_text((72, 72), "hello text")
    img = Image.new("RGB", (50, 50), color="white")
    draw = ImageDraw.Draw(img)
    draw.rectangle((10, 10, 40, 40), fill="black")
    img_path = path.with_suffix(".png")
    img.save(img_path)
    rect = fitz.Rect(0, 0, 50, 50)
    page.insert_image(rect, filename=str(img_path))
    doc.save(path)
    doc.close()
    img_path.unlink()  # cleanup


def test_parse_pdf_text_only(monkeypatch, tmp_path):
    pdf_path = tmp_path / "text.pdf"
    _create_text_pdf(pdf_path)

    fake_md = types.SimpleNamespace(to_markdown=lambda p: "text only")
    monkeypatch.setitem(sys.modules, "pymupdf4llm", fake_md)
    monkeypatch.setattr(parser, "ocr_image_file", lambda p: "img text")

    result = parser.parse_pdf(str(pdf_path))
    assert "附录" not in result


def test_parse_pdf_scanned_only(monkeypatch, tmp_path):
    pdf_path = tmp_path / "scan.pdf"
    _create_pdf_with_image(pdf_path, with_text=False)

    fake_md = types.SimpleNamespace(to_markdown=lambda p: "")
    monkeypatch.setitem(sys.modules, "pymupdf4llm", fake_md)
    monkeypatch.setattr(parser, "ocr_image_file", lambda p: "img text")

    result = parser.parse_pdf(str(pdf_path))
    assert "附录" in result


def test_parse_pdf_mixed(monkeypatch, tmp_path):
    pdf_path = tmp_path / "mixed.pdf"
    _create_pdf_with_image(pdf_path, with_text=True)

    fake_md = types.SimpleNamespace(to_markdown=lambda p: "some text")
    monkeypatch.setitem(sys.modules, "pymupdf4llm", fake_md)
    monkeypatch.setattr(parser, "ocr_image_file", lambda p: "img text")

    result = parser.parse_pdf(str(pdf_path))
    assert "附录" in result

