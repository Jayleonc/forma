from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from PIL import Image, ImageDraw

from forma.conversion.processors.xlsx import XlsxProcessor


def _create_demo_xlsx(path: Path) -> None:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Products"
    worksheet.append(["SKU", "Name", "Status"])
    worksheet.append(["SKU-001", "Portable Fan", "active"])

    image_path = path.with_suffix(".png")
    image = Image.new("RGB", (60, 40), color="white")
    draw = ImageDraw.Draw(image)
    draw.text((5, 10), "fan", fill="black")
    image.save(image_path)

    worksheet.add_image(XLImage(str(image_path)), "B2")
    workbook.save(path)
    image_path.unlink()


def test_xlsx_processor_extracts_visual_assets(tmp_path):
    xlsx_path = tmp_path / "inventory.xlsx"
    _create_demo_xlsx(xlsx_path)

    result = XlsxProcessor().process(xlsx_path)

    assert "| SKU | Name | Status |" in result.markdown_content
    assert result.image_count == 1
    assert len(result.visual_assets) == 1

    asset = result.visual_assets[0]
    assert asset.position_type == "tabular_anchor"
    assert asset.position_meta["sheet"] == "Products"
    assert asset.position_meta["from_row"] == 2
    assert asset.position_meta["from_col"] == 2
    assert asset.position_meta["from_col_label"] == "B"
    assert asset.position_meta["context_text"] == "SKU=SKU-001; Name=Portable Fan; Status=active"
    assert "row 2" in asset.alt_text
    assert "Portable Fan" in asset.alt_text
