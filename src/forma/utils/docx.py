from typing import Iterator, Union
from docx import Document  # type: ignore
from docx.document import Document as DocumentObject
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import _Cell, Table
from docx.text.paragraph import Paragraph


def _escape_pipes(text: str) -> str:
    """Escapes pipe characters in text to be used in Markdown tables."""
    return text.replace("|", r"\|").replace("\n", "<br>")


def _table_to_markdown(table: Table) -> str:
    """Converts a docx Table object to a GFM Markdown table."""
    rows_cells = []
    for row in table.rows:
        # Using a set to handle merged cells by only processing unique cell content once
        unique_cells = set()
        row_texts = []
        for cell in row.cells:
            if cell._tc not in unique_cells:
                row_texts.append(_escape_pipes(cell.text.strip()))
                unique_cells.add(cell._tc)
        
        # Trim trailing empty cells to keep tables clean
        while row_texts and not row_texts[-1].strip():
            row_texts.pop()
        rows_cells.append(row_texts or [""])

    if not rows_cells:
        return ""

    # Unify column count for all rows
    max_cols = max(len(r) for r in rows_cells)
    full_rows = [r + [""] * (max_cols - len(r)) for r in rows_cells]

    header = full_rows[0]
    separator = ["---"] * max_cols
    body = full_rows[1:] if len(full_rows) > 1 else []

    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(separator) + " |",
    ]
    for r in body:
        lines.append("| " + " | ".join(r) + " |")
    
    # Add a note for potentially complex tables
    has_merged_cells = any(len(set(c._tc for c in r.cells)) != len(r.cells) for r in table.rows)
    if has_merged_cells:
        lines.insert(0, "> _此表包含合并单元格，Markdown 展示可能有信息丢失，请参考原文。_\n")

    return "\n".join(lines)


def iter_block_items(parent: Union[DocumentObject, _Cell]) -> Iterator[Union[Paragraph, Table]]:
    """
    Yields each paragraph and table child within *parent*,
    in document order. *parent* can be a `Document` or a `_Cell`.
    """
    if isinstance(parent, DocumentObject):
        parent_elm = parent.element.body
    elif isinstance(parent, _Cell):
        parent_elm = parent._tc
    else:
        raise ValueError("Unsupported parent type")

    for child in parent_elm.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, parent)
        elif isinstance(child, CT_Tbl):
            yield Table(child, parent)


def docx_to_markdown_gfm(path: str) -> str:
    """Converts a DOCX file to Markdown using python-docx (Plan A)."""
    doc = Document(path)
    parts = []
    for block in iter_block_items(doc):
        if isinstance(block, Paragraph):
            txt = block.text.strip()
            if txt:
                parts.append(txt)
        elif isinstance(block, Table):
            md_table = _table_to_markdown(block)
            if md_table:
                parts.append(md_table)

    return "\n\n".join(p for p in parts if p)
