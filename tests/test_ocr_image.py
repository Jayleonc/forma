from __future__ import annotations

from pathlib import Path
import types
import sys

from PIL import Image, ImageDraw

from forma.core.ocr import ocr_image_file


def _create_image(path: Path, text: str | None = None) -> None:
    img = Image.new("RGB", (100, 50), color="white")
    if text:
        draw = ImageDraw.Draw(img)
        draw.text((10, 10), text, fill="black")
    img.save(path)


def test_ocr_image_file(monkeypatch, tmp_path):
    normal_path = tmp_path / "normal.png"
    blank_path = tmp_path / "blank.png"
    _create_image(normal_path, "hello")
    _create_image(blank_path)

    calls = {"count": 0}

    class DummyOCR:
        def __init__(self, *args, **kwargs):
            calls["count"] += 1

        def ocr(self, image_path: str, cls: bool = True):  # noqa: D401
            if "blank" in image_path:
                return []
            return [[{"text": "hello"}, {"text": "world"}]]

    monkeypatch.setitem(
        sys.modules, "paddleocr", types.SimpleNamespace(PaddleOCR=DummyOCR)
    )
    monkeypatch.setattr("forma.core.ocr._OCR_ENGINE", None, raising=False)

    result_normal = ocr_image_file(str(normal_path))
    result_blank = ocr_image_file(str(blank_path))

    assert result_normal == "hello\nworld"
    assert result_blank == ""
    assert calls["count"] == 1  # singleton check

