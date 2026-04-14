"""Document reading and normalization for DOCX/PDF files."""

import re
import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

from docx import Document
import pdfplumber


# ── Shared text utilities ─────────────────────────────────────────────

def normalize_ws(text: str) -> str:
    """Collapse whitespace to single spaces and strip."""
    return re.sub(r"\s+", " ", text or "").strip()


def normalize_text(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"\r\n|\r", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_document(document):
    if isinstance(document, str):
        return normalize_text(document)
    paragraphs = []
    for para in document.get("paragraphs", []):
        text = normalize_text(para.get("text", ""))
        display_text = normalize_text(para.get("display_text") or text)
        if not display_text:
            continue
        normalized = dict(para)
        normalized["text"] = text
        normalized["display_text"] = display_text
        paragraphs.append(normalized)
    return {
        **document,
        "paragraphs": paragraphs,
        "text": "\n".join(p["display_text"] for p in paragraphs),
    }


# ── DOCX XML helpers ─────────────────────────────────────────────────

W_URI = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W_NS = {"w": W_URI}


def _w_attr(name: str) -> str:
    return f"{{{W_URI}}}{name}"


def _read_docx_xml(path: Path, inner_path: str):
    with zipfile.ZipFile(path) as zf:
        try:
            data = zf.read(inner_path)
        except KeyError:
            return None
    return ET.fromstring(data)


def _parse_docx_style_map(path: Path) -> dict:
    tree = _read_docx_xml(path, "word/styles.xml")
    if tree is None:
        return {}
    styles = {}
    for style in tree.findall(".//w:style", W_NS):
        style_id = style.get(_w_attr("styleId"))
        if not style_id:
            continue
        name_el = style.find("w:name", W_NS)
        based_on_el = style.find("w:basedOn", W_NS)
        num_pr = style.find("w:pPr/w:numPr", W_NS)
        num_id, ilvl = None, None
        if num_pr is not None:
            nid_el = num_pr.find("w:numId", W_NS)
            il_el = num_pr.find("w:ilvl", W_NS)
            if nid_el is not None:
                num_id = nid_el.get(_w_attr("val"))
            if il_el is not None:
                ilvl = il_el.get(_w_attr("val"))
        styles[style_id] = {
            "style_id": style_id,
            "style_name": name_el.get(_w_attr("val")) if name_el is not None else style_id,
            "based_on": based_on_el.get(_w_attr("val")) if based_on_el is not None else None,
            "num_id": int(num_id) if num_id is not None else None,
            "ilvl": int(ilvl) if ilvl is not None else None,
        }
    return styles


def _resolve_style_numbering(style_id, style_map, seen=None):
    if not style_id or style_id not in style_map:
        return None, None
    seen = seen or set()
    if style_id in seen:
        return None, None
    seen.add(style_id)
    info = style_map[style_id]
    if info["num_id"] is not None:
        return info["num_id"], info["ilvl"] if info["ilvl"] is not None else 0
    return _resolve_style_numbering(info["based_on"], style_map, seen)


def _parse_docx_numbering(path: Path) -> dict:
    tree = _read_docx_xml(path, "word/numbering.xml")
    numbering = {"num_to_abstract": {}, "abstract_levels": {}}
    if tree is None:
        return numbering
    for abstract in tree.findall("w:abstractNum", W_NS):
        abstract_id = abstract.get(_w_attr("abstractNumId"))
        if abstract_id is None:
            continue
        levels = {}
        for lvl in abstract.findall("w:lvl", W_NS):
            ilvl_raw = lvl.get(_w_attr("ilvl"))
            if ilvl_raw is None:
                continue
            start_el = lvl.find("w:start", W_NS)
            fmt_el = lvl.find("w:numFmt", W_NS)
            text_el = lvl.find("w:lvlText", W_NS)
            levels[int(ilvl_raw)] = {
                "start": int(start_el.get(_w_attr("val"))) if start_el is not None else 1,
                "num_fmt": fmt_el.get(_w_attr("val")) if fmt_el is not None else "decimal",
                "lvl_text": text_el.get(_w_attr("val")) if text_el is not None else f"%{int(ilvl_raw) + 1}",
            }
        numbering["abstract_levels"][int(abstract_id)] = levels
    for num in tree.findall("w:num", W_NS):
        num_id = num.get(_w_attr("numId"))
        abstract_el = num.find("w:abstractNumId", W_NS)
        if num_id is None or abstract_el is None:
            continue
        numbering["num_to_abstract"][int(num_id)] = int(abstract_el.get(_w_attr("val")))
    return numbering


# ── Numbering format helpers ─────────────────────────────────────────

def _to_roman(value: int) -> str:
    pairs = [
        (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"),
        (90, "XC"), (50, "L"), (40, "XL"), (10, "X"), (9, "IX"),
        (5, "V"), (4, "IV"), (1, "I"),
    ]
    result, remaining = [], max(1, value)
    for arabic, roman in pairs:
        while remaining >= arabic:
            result.append(roman)
            remaining -= arabic
    return "".join(result)


def _to_alpha(value: int, uppercase=False) -> str:
    chars, remaining = [], max(1, value)
    while remaining > 0:
        remaining -= 1
        chars.append(chr(ord("A" if uppercase else "a") + (remaining % 26)))
        remaining //= 26
    return "".join(reversed(chars))


def _format_counter(value: int, num_fmt: str) -> str:
    if num_fmt in {"upperRoman", "romanUpper"}:
        return _to_roman(value)
    if num_fmt in {"lowerRoman", "romanLower"}:
        return _to_roman(value).lower()
    if num_fmt == "upperLetter":
        return _to_alpha(value, True)
    if num_fmt == "lowerLetter":
        return _to_alpha(value, False)
    return str(value)


def _render_numbering_label(num_id, ilvl, numbering_data, counters_by_num):
    abstract_id = numbering_data["num_to_abstract"].get(num_id)
    levels = numbering_data["abstract_levels"].get(abstract_id, {}) if abstract_id is not None else {}
    level_info = levels.get(ilvl, {})
    counters = counters_by_num[num_id]
    start = level_info.get("start", 1)
    counters[ilvl] = counters.get(ilvl, start - 1) + 1
    for level in list(counters):
        if level > ilvl:
            del counters[level]
    label = level_info.get("lvl_text", f"%{ilvl + 1}")
    path_parts = []
    for level in range(ilvl + 1):
        if level not in counters:
            continue
        num_fmt = levels.get(level, {}).get("num_fmt", "decimal")
        formatted = _format_counter(counters[level], num_fmt)
        label = label.replace(f"%{level + 1}", formatted)
        path_parts.append(formatted)
    return re.sub(r"\s+", " ", label).strip(), path_parts


def _extract_paragraph_numbering(paragraph):
    p_pr = paragraph._p.pPr
    num_pr = p_pr.numPr if p_pr is not None else None
    if num_pr is None:
        return None, None
    num_id_el, ilvl_el = num_pr.numId, num_pr.ilvl
    return (
        int(num_id_el.val) if num_id_el is not None else None,
        int(ilvl_el.val) if ilvl_el is not None else 0,
    )


def _get_heading_level(style_name, style_id):
    for candidate in (style_name, style_id):
        if not candidate:
            continue
        normalized = re.sub(r"\s+", "", candidate).lower()
        if normalized.startswith("heading") and normalized[7:].isdigit():
            return int(normalized[7:])
    return None


# ── Document readers ─────────────────────────────────────────────────

def read_docx_document(path: Path) -> dict:
    doc = Document(path)
    style_map = _parse_docx_style_map(path)
    numbering_data = _parse_docx_numbering(path)
    counters_by_num = defaultdict(dict)
    paragraphs = []
    for idx, paragraph in enumerate(doc.paragraphs):
        text = paragraph.text.strip()
        if not text:
            continue
        style_name = paragraph.style.name if paragraph.style else None
        style_id = paragraph.style.style_id if paragraph.style else None
        heading_level = _get_heading_level(style_name, style_id)
        num_id, ilvl = _extract_paragraph_numbering(paragraph)
        if num_id is None:
            num_id, ilvl = _resolve_style_numbering(style_id, style_map)
        numbering_label, numbering_path = None, []
        if num_id is not None and ilvl is not None:
            numbering_label, numbering_path = _render_numbering_label(
                num_id, ilvl, numbering_data, counters_by_num,
            )
        display_text = text
        if heading_level in {1, 2, 3} and numbering_label:
            display_text = f"{numbering_label} {text}".strip()
        paragraphs.append({
            "idx": idx, "text": text, "display_text": display_text,
            "style_name": style_name, "style_id": style_id,
            "heading_level": heading_level, "num_id": num_id, "ilvl": ilvl,
            "numbering_label": numbering_label, "numbering_path": numbering_path,
        })
    return {
        "kind": "docx",
        "text": "\n".join(p["display_text"] for p in paragraphs),
        "paragraphs": paragraphs,
    }


def read_pdf_text(path: Path) -> str:
    pages = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages.append(text.strip())
    return "\n".join(pages)


def read_document(path: Path) -> dict:
    ext = path.suffix.lower()
    if ext == ".docx":
        return read_docx_document(path)
    if ext == ".pdf":
        text = read_pdf_text(path)
        paragraphs = [
            {
                "idx": i, "text": l.strip(), "display_text": l.strip(),
                "style_name": None, "style_id": None, "heading_level": None,
                "num_id": None, "ilvl": None,
                "numbering_label": None, "numbering_path": [],
            }
            for i, l in enumerate(text.splitlines()) if l.strip()
        ]
        return {"kind": "pdf", "text": text, "paragraphs": paragraphs}
    raise ValueError(f"Khong ho tro dinh dang: {ext}")


# ── Convenience ──────────────────────────────────────────────────────

def read_and_normalize(path: Path) -> dict:
    """Read a DOCX/PDF file and return a normalized document dict."""
    raw = read_document(path)
    return normalize_document(raw)
