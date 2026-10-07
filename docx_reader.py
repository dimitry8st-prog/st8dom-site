"""Безопасное чтение локальных DOCX для онлайн-версии библиотеки."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from zipfile import BadZipFile, ZipFile
import xml.etree.ElementTree as ET


WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": WORD_NS}
W = f"{{{WORD_NS}}}"


def _node_text(node: ET.Element) -> str:
    parts: list[str] = []
    for child in node.iter():
        if child.tag == f"{W}t" and child.text:
            parts.append(child.text)
        elif child.tag == f"{W}tab":
            parts.append(" ")
        elif child.tag == f"{W}br":
            parts.append("\n")
    return "".join(parts).strip()


def _paragraph_block(paragraph: ET.Element, style_names: dict[str, str] | None = None) -> dict | None:
    text = _node_text(paragraph)
    if not text:
        return None

    style_node = paragraph.find("w:pPr/w:pStyle", NS)
    style = style_node.get(f"{W}val", "") if style_node is not None else ""
    style = (style_names or {}).get(style, style)
    style_lower = style.casefold()
    has_numbering = paragraph.find("w:pPr/w:numPr", NS) is not None

    if style_lower.startswith("heading"):
        suffix = "".join(character for character in style if character.isdigit())
        level = 2 if suffix in {"", "1"} else 3
        return {"type": "heading", "level": level, "text": text}
    if style_lower == "title":
        return {"type": "heading", "level": 2, "text": text}
    if style_lower.startswith(("list", "bullet")) or has_numbering:
        return {"type": "list_item", "text": text}
    return {"type": "paragraph", "text": text}


def _table_block(table: ET.Element) -> dict | None:
    rows: list[list[str]] = []
    for row in table.findall("w:tr", NS):
        cells = ["\n".join(_node_text(p) for p in cell.findall("w:p", NS)).strip()
                 for cell in row.findall("w:tc", NS)]
        if any(cells):
            rows.append(cells)
    if not rows:
        return None
    width = max(len(row) for row in rows)
    normalized = [row + [""] * (width - len(row)) for row in rows]
    return {"type": "table", "header": normalized[0], "rows": normalized[1:]}


def _group_lists(blocks: list[dict]) -> list[dict]:
    grouped: list[dict] = []
    for block in blocks:
        if block["type"] == "list_item":
            if grouped and grouped[-1]["type"] == "list":
                grouped[-1]["items"].append(block["text"])
            else:
                grouped.append({"type": "list", "items": [block["text"]]})
        else:
            grouped.append(block)
    return grouped


@lru_cache(maxsize=32)
def read_docx_blocks(filename: str) -> list[dict]:
    """Возвращает абзацы, заголовки, списки и таблицы из локального DOCX."""
    path = Path(filename)
    if not path.is_file():
        raise FileNotFoundError(path)
    try:
        with ZipFile(path) as archive:
            xml = archive.read("word/document.xml")
            style_names = {}
            if "word/styles.xml" in archive.namelist():
                styles = ET.fromstring(archive.read("word/styles.xml"))
                for style in styles.findall("w:style", NS):
                    name = style.find("w:name", NS)
                    if name is not None:
                        style_names[style.get(f"{W}styleId", "")] = name.get(f"{W}val", "")
    except (BadZipFile, KeyError) as exc:
        raise ValueError(f"Некорректный DOCX: {path.name}") from exc

    root = ET.fromstring(xml)
    body = root.find("w:body", NS)
    if body is None:
        return []

    blocks: list[dict] = []
    for child in body:
        block = None
        if child.tag == f"{W}p":
            block = _paragraph_block(child, style_names)
        elif child.tag == f"{W}tbl":
            rows = child.findall("w:tr", NS)
            if len(rows) == 1 and len(rows[0].findall("w:tc", NS)) == 1:
                for paragraph in rows[0].findall("w:tc/w:p", NS):
                    paragraph_block = _paragraph_block(paragraph, style_names)
                    if paragraph_block:
                        blocks.append(paragraph_block)
                continue
            block = _table_block(child)
        if block:
            blocks.append(block)
    return _group_lists(blocks)
