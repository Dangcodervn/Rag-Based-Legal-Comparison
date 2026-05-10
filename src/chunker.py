"""Chunk documents by Vietnamese legal structure (Dieu/Khoan/Diem)."""

import re
from datetime import datetime, timezone


# ── Regex patterns ───────────────────────────────────────────────────

CHUONG_RE = re.compile(r"^Chương\s+([IVXLCDM\d]+)[\.:]?\s*(.*)", re.IGNORECASE)
MUC_RE = re.compile(r"^Mục\s+(\d+)[\.:]?\s*(.*)", re.IGNORECASE)
DIEU_RE = re.compile(
    r"^(?:Điều|ĐIỀU|dieu|DIEU)\s+((?:\d+[A-Za-z]?|[IVXLCDM]+))[\.:]?\s*(.*)$"
)
KHOAN_RE = re.compile(r"^(\d+)[\.)]\s*(.*)$")
DIEM_RE = re.compile(r"^([a-zđ])[\.)]\s*(.*)$", re.IGNORECASE)
DINH_NGHIA_RE = re.compile(r"giải thích từ ngữ|định nghĩa|diễn giải", re.IGNORECASE)


# ── Heading detection helpers ────────────────────────────────────────

def _clean_heading(line):
    return re.sub(r"[:\s]+$", "", line.strip())


def _looks_upper_heading(line):
    s = line.strip()
    if not s or s.endswith((".", ";", ",", ":")):
        return False
    if any(ch.isdigit() for ch in s):
        return False
    words = s.split()
    if len(words) < 2 or len(words) > 14:
        return False
    letters = [ch for ch in s if ch.isalpha()]
    return bool(letters) and sum(ch.isupper() for ch in letters) / len(letters) >= 0.8


def _looks_title_heading(line):
    s = line.strip()
    if not s or s.endswith((".", ";", ",", ":")):
        return False
    if any(ch.isdigit() for ch in s):
        return False
    if any(ch in s for ch in ('"', "'", "(", ")", "-", "•", "*")):
        return False
    words = [re.sub(r"[^\wÀ-ỹĐđ-]", "", w) for w in s.split()]
    words = [w for w in words if w]
    if len(words) < 2 or len(words) > 14:
        return False
    return sum(1 for w in words if w[0].isupper()) >= max(2, len(words) - 1)


def _is_contract_section_heading(line):
    s = line.strip()
    if not s:
        return False
    if CHUONG_RE.match(s) or MUC_RE.match(s) or DIEU_RE.match(s):
        return False
    if KHOAN_RE.match(s) or DIEM_RE.match(s):
        return False
    if s.startswith(("(", "-", "•", "*", '"', "\u201c")):
        return False
    if len(s) > 120:
        return False
    return _looks_upper_heading(s) or _looks_title_heading(s)


# Common Vietnamese sentence starters that indicate body text (not section titles)
_VI_BODY_OPENERS = {
    'các', 'mọi', 'nếu', 'khi', 'theo', 'với', 'để', 'trong', 'do', 'vì',
    'bởi', 'tuy', 'mặc', 'dù', 'nhưng', 'và', 'hoặc', 'việc', 'sự', 'những',
    'một', 'hai', 'ba', 'quy', 'qui', 'điều', 'khoản', 'trường', 'trừ',
    'căn', 'dựa', 'theo', 'sau', 'trước', 'trong', 'tại', 'đối',
}


def _looks_vi_section_title(line: str) -> bool:
    """Detect a standalone unnumbered section heading in Vietnamese DOCX context.

    Used for paragraphs with no heading_level and no numbering_label that appear
    inside a numbered-article document (i.e., added without proper Word styling).
    """
    s = line.strip()
    if not s:
        return False
    # Must not end with sentence-ending punctuation
    if s[-1] in '.;,?!:':
        return False
    # Must not contain parentheses (often inline expressions, not titles)
    if '(' in s or ')' in s:
        return False
    words = s.split()
    if len(words) < 2 or len(words) > 12:
        return False
    # First word must start with uppercase (Vietnamese title style: only first word caps)
    if not words[0][0].isupper():
        return False
    # Must not start with a known body-text opener
    if words[0].lower() in _VI_BODY_OPENERS:
        return False
    return True


# ── Khoan/Diem extraction ───────────────────────────────────────────

def _extract_khoan_items(body_lines):
    items, current = [], None
    for raw in body_lines:
        line = raw.strip()
        if not line:
            if current and current["text"]:
                current["text"] += "\n"
            continue
        km = KHOAN_RE.match(line)
        if km:
            if current:
                current["text"] = current["text"].strip()
                items.append(current)
            current = {
                "khoan_number": km.group(1),
                "text": km.group(2).strip(),
                "diem_items": [],
                "tieu_muc_items": [],
            }
            continue
        dm = DIEM_RE.match(line)
        if dm and current is not None:
            diem_val = dm.group(1).strip()
            current["diem_items"].append({
                "diem_number": diem_val,
                "diem_key": diem_val,
                "text": dm.group(2).strip(),
            })
            current["text"] = (current["text"] + "\n" + line).strip()
            continue
        if current is not None:
            current["text"] = (current["text"] + "\n" + line).strip()
    if current:
        current["text"] = current["text"].strip()
        items.append(current)
    return items


# ── Chunk builder ────────────────────────────────────────────────────

def _build_chunk(
    *, chunk_idx, doc_id, version, chuong_so, muc_so,
    clause_id, article_number, article_title, text,
    khoan_items=None, is_header=False,
):
    khoan_items = khoan_items or []
    diem_count = sum(len(i.get("diem_items", [])) for i in khoan_items)
    tieu_muc_count = sum(len(i.get("tieu_muc_items", [])) for i in khoan_items)
    return {
        "chunk_id": f"{doc_id}_{version}_{chunk_idx:04d}",
        "doc_id": doc_id,
        "version": version,
        "chunk_type": "definition" if DINH_NGHIA_RE.search(article_title) else "article",
        "chuong_so": chuong_so,
        "muc_so": muc_so,
        "clause_id": clause_id,
        "article_number": article_number,
        "article_title": article_title,
        "khoan_count": 0 if is_header else len(khoan_items),
        "diem_count": 0 if is_header else diem_count,
        "tieu_muc_count": 0 if is_header else tieu_muc_count,
        "khoan_items": [] if is_header else khoan_items,
        "text": text,
        "char_len": len(text),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


# ── DOCX heading-based chunking ─────────────────────────────────────

def _chunk_docx_headings(document, doc_id, version):
    paragraphs = document.get("paragraphs", [])
    chunks, chunk_idx = [], 1
    article_state = {
        "article_number": "0",
        "article_title": "Phần mở đầu",
        "heading_display": "",
        "body_lines": [],
        "khoan_items": [],
    }
    current_khoan, current_tieu_muc = None, None
    auto_sec_idx = 0  # counter for auto-numbered unnumbered sections
    has_seen_numbered = False  # flag: we've entered at least one numbered article

    def flush():
        nonlocal article_state, current_khoan, current_tieu_muc, chunk_idx
        if article_state is None:
            return
        block = "\n".join(
            l for l in [article_state["heading_display"]] + article_state["body_lines"]
            if l.strip()
        ).strip()
        if block:
            chunks.append(_build_chunk(
                chunk_idx=chunk_idx, doc_id=doc_id, version=version,
                chuong_so="0", muc_so="0",
                clause_id=f"article_{article_state['article_number']}",
                article_number=article_state["article_number"],
                article_title=article_state["article_title"],
                text=block, khoan_items=article_state["khoan_items"],
            ))
            chunk_idx += 1
        article_state = current_khoan = current_tieu_muc = None

    for para in paragraphs:
        text = para.get("text", "").strip()
        dt = para.get("display_text") or text
        hl = para.get("heading_level")
        nl = para.get("numbering_label")
        np_ = para.get("numbering_path") or []

        if hl == 1 and nl:
            flush()
            has_seen_numbered = True
            article_state = {
                "article_number": np_[0] if np_ else nl.rstrip("."),
                "article_title": _clean_heading(text),
                "heading_display": dt.strip(),
                "body_lines": [],
                "khoan_items": [],
            }
            continue

        # Unnumbered H1 heading (heading style but no list number)
        if hl == 1 and not nl:
            flush()
            auto_sec_idx += 1
            article_state = {
                "article_number": f"S{auto_sec_idx}",
                "article_title": _clean_heading(text),
                "heading_display": dt.strip(),
                "body_lines": [],
                "khoan_items": [],
            }
            continue

        # Plain-text paragraph that looks like a standalone Vietnamese section title
        # (added without Word heading style - common when editing DOCX manually)
        if hl is None and not nl and has_seen_numbered and _looks_vi_section_title(text):
            flush()
            auto_sec_idx += 1
            article_state = {
                "article_number": f"S{auto_sec_idx}",
                "article_title": _clean_heading(text),
                "heading_display": dt.strip(),
                "body_lines": [],
                "khoan_items": [],
            }
            continue

        if hl == 2 and nl:
            current_khoan = {
                "khoan_number": nl.rstrip("."),
                "title": _clean_heading(text),
                "text": dt.strip(),
                "diem_items": [],
                "tieu_muc_items": [],
            }
            current_tieu_muc = None
            article_state["khoan_items"].append(current_khoan)
            article_state["body_lines"].append(dt.strip())
            continue
        if hl == 3 and nl:
            if current_khoan is None:
                syn = ".".join(np_[:2]) if len(np_) >= 2 else nl.rstrip(".")
                current_khoan = {
                    "khoan_number": syn, "title": "", "text": "",
                    "diem_items": [], "tieu_muc_items": [],
                }
                article_state["khoan_items"].append(current_khoan)
            current_tieu_muc = {
                "tieu_muc_number": nl.rstrip("."),
                "title": _clean_heading(text),
                "text": dt.strip(),
            }
            current_khoan["tieu_muc_items"].append(current_tieu_muc)
            current_khoan["text"] = "\n".join(
                p for p in [current_khoan["text"], dt.strip()] if p
            ).strip()
            article_state["body_lines"].append(dt.strip())
            continue

        article_state["body_lines"].append(dt.strip())
        if current_tieu_muc is not None:
            current_tieu_muc["text"] = (current_tieu_muc["text"] + "\n" + dt.strip()).strip()
            current_khoan["text"] = (current_khoan["text"] + "\n" + dt.strip()).strip()
        elif current_khoan is not None:
            current_khoan["text"] = (current_khoan["text"] + "\n" + dt.strip()).strip()

    flush()
    return chunks


# ── Plain-text chunking ──────────────────────────────────────────────

def _chunk_plain_text(text, doc_id, version):
    lines = [l for l in text.split("\n") if l.strip()]
    chunks, chunk_idx, section_seq = [], 1, 1
    cur_chuong, cur_muc = "0", "0"
    use_explicit = sum(1 for l in lines if DIEU_RE.match(l.strip())) > 0
    cur_no = cur_cid = None
    cur_head, cur_title, cur_body = [], [], []
    preamble_done = False

    # ── Pre-pass: collect preamble before first Điều/Chương/Mục ─────
    first_structural = next(
        (i for i, l in enumerate(lines)
         if DIEU_RE.match(l.strip()) or CHUONG_RE.match(l.strip()) or MUC_RE.match(l.strip())),
        None,
    )
    if first_structural and first_structural > 0:
        preamble_text = "\n".join(lines[:first_structural]).strip()
        if preamble_text:
            chunks.append(_build_chunk(
                chunk_idx=chunk_idx, doc_id=doc_id, version=version,
                chuong_so="0", muc_so="0", clause_id="article_0",
                article_number="0", article_title="Phần mở đầu",
                text=preamble_text, khoan_items=[],
            ))
            chunk_idx += 1
        lines = lines[first_structural:]

    def start(heading, article_number=None, title_text=None):
        nonlocal cur_no, cur_cid, cur_head, cur_title, cur_body, section_seq
        if article_number is None:
            cur_no, cur_cid = str(section_seq), f"section_{section_seq:03d}"
            section_seq += 1
        else:
            cur_no, cur_cid = str(article_number), f"article_{article_number}"
        cur_head = [heading.strip()]
        cur_title = [_clean_heading(title_text or heading)] if (title_text or heading).strip() else []
        cur_body = []

    def flush():
        nonlocal chunk_idx, cur_no, cur_cid, cur_head, cur_title, cur_body
        if cur_no is None:
            return
        if cur_cid.startswith("section_") and not any(l.strip() for l in cur_body):
            cur_no = cur_cid = None
            cur_head = cur_title = cur_body = []
            return
        block = "\n".join(l for l in cur_head + cur_body if l.strip()).strip()
        if not block:
            cur_no = cur_cid = None
            cur_head = cur_title = cur_body = []
            return
        at = " - ".join(l for l in cur_title if l.strip()) or " - ".join(
            _clean_heading(l) for l in cur_head
        )
        chunks.append(_build_chunk(
            chunk_idx=chunk_idx, doc_id=doc_id, version=version,
            chuong_so=cur_chuong, muc_so=cur_muc, clause_id=cur_cid,
            article_number=cur_no, article_title=at,
            text=block, khoan_items=_extract_khoan_items(cur_body),
        ))
        chunk_idx += 1
        cur_no = cur_cid = None
        cur_head = cur_title = cur_body = []

    for line in lines:
        s = line.strip()
        mc = CHUONG_RE.match(s)
        mm = MUC_RE.match(s)
        md = DIEU_RE.match(s)
        if mc:
            flush()
            cur_chuong = mc.group(1)
            cur_muc = "0"
            preamble_done = True
            continue
        if mm:
            flush()
            cur_muc = mm.group(1)
            preamble_done = True
            continue
        if md:
            flush()
            start(s, article_number=md.group(1),
                  title_text=md.group(2).strip() or f"Điều {md.group(1)}")
            preamble_done = True
            continue
        if use_explicit:
            if cur_no is not None:
                cur_body.append(s)
            continue
        if _is_contract_section_heading(s) and preamble_done:
            if cur_no is None:
                start(s)
            elif cur_body:
                flush()
                start(s)
            else:
                cur_head.append(s)
                cur_title.append(_clean_heading(s))
            continue
        if cur_no is not None:
            cur_body.append(s)

    flush()
    return chunks


# ── Public API ───────────────────────────────────────────────────────

def chunk_document(document, doc_id: str, version: str) -> list[dict]:
    """Chunk a normalized document into article-level chunks."""
    if isinstance(document, dict):
        paragraphs = document.get("paragraphs", [])
        has_headings = sum(
            1 for p in paragraphs
            if p.get("heading_level") == 1 and p.get("numbering_label")
        ) > 0
        if has_headings:
            return _chunk_docx_headings(document, doc_id, version)
        return _chunk_plain_text(document.get("text", ""), doc_id, version)
    return _chunk_plain_text(document, doc_id, version)


def explode_to_khoan_chunks(chunks: list[dict]) -> list[dict]:
    """Expand article-level chunks into one chunk per Khoản.

    Each output chunk has:
    - article_number = "{dieu}.{khoan}" composite key (e.g. "1.2")
    - dieu_number    = original Điều number (e.g. "1")
    - khoan_number   = Khoản number (e.g. "2")
    - text           = the Khoản's body text

    Chunks without khoan_items are passed through with khoan_number="0".
    """
    result = []
    for chunk in chunks:
        dieu_no = str(chunk.get('article_number', ''))
        khoan_items = chunk.get('khoan_items') or []

        if not khoan_items:
            out = dict(chunk)
            out['dieu_number'] = dieu_no
            out['khoan_number'] = '0'
            result.append(out)
            continue

        for khoan in khoan_items:
            khoan_no = str(khoan.get('khoan_number', '')).strip()
            if not khoan_no:
                continue
            khoan_text = khoan.get('text', '').strip()
            if not khoan_text:
                continue
            out = dict(chunk)
            out['chunk_id'] = f"{chunk['chunk_id']}_k{khoan_no}"
            out['article_number'] = f"{dieu_no}.{khoan_no}"
            out['dieu_number'] = dieu_no
            out['khoan_number'] = khoan_no
            out['text'] = khoan_text
            out['char_len'] = len(khoan_text)
            out['khoan_items'] = []
            result.append(out)

    return result
