from __future__ import annotations

from pathlib import Path
import types

from pptx import Presentation
from pptx.util import Inches
from PIL import Image, ImageDraw

from forma.core.processors import PptxProcessor


def _create_demo_pptx(path: Path) -> None:
    prs = Presentation()
    layout = prs.slide_layouts[5]  # blank

    # Slide 0: fast path with plenty of text and one image
    slide_fast = prs.slides.add_slide(layout)
    tb = slide_fast.shapes.add_textbox(Inches(1), Inches(1), Inches(8), Inches(2))
    tb.text_frame.text = "This slide has enough textual content to avoid the deep path."

    img = Image.new("RGB", (50, 50), color="white")
    draw = ImageDraw.Draw(img)
    draw.text((5, 5), "hi", fill="black")
    img_path = path.with_suffix(".png")
    img.save(img_path)
    slide_fast.shapes.add_picture(str(img_path), Inches(1), Inches(2))
    img_path.unlink()

    # Slide 1: complex path with very little text
    slide_complex = prs.slides.add_slide(layout)
    tb2 = slide_complex.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(1))
    tb2.text_frame.text = "Hi"

    prs.save(path)


def test_pptx_processor(monkeypatch, tmp_path):
    pptx_path = tmp_path / "demo.pptx"
    _create_demo_pptx(pptx_path)

    # Stub image OCR
    monkeypatch.setattr(
        "forma.core.processors.parse_image_to_markdown", lambda p: "image md"
    )

    # Stub VLM parser
    calls = {"vlm": 0}

    class DummyVlm:
        def parse(self, path, prompt_name: str = "default_image_description"):
            calls["vlm"] += 1
            return "vlm slide"

    monkeypatch.setattr("forma.core.processors.VlmParser", DummyVlm)

    # Stub LibreOffice conversion
    def fake_run(cmd, check, stdout=None, stderr=None):
        outdir = Path(cmd[cmd.index("--outdir") + 1])
        out_pdf = outdir / (Path(cmd[-1]).stem + ".pdf")
        import fitz

        doc = fitz.open()
        doc.new_page()
        doc.new_page()
        doc.save(out_pdf)
        doc.close()
        return types.SimpleNamespace(returncode=0)

    monkeypatch.setattr("subprocess.run", fake_run)

    processor = PptxProcessor()
    result = processor.process(pptx_path)

    assert "image md" in result.markdown_content
    assert "vlm slide" in result.markdown_content
    assert calls["vlm"] == 1

