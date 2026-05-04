"""LLM-based article comparison with evidence grounding."""

import difflib
import json
import re
from collections import Counter
from pathlib import Path

try:
    import ollama
except ImportError:
    ollama = None

from src.ingest import normalize_ws
from src.retriever import (
    article_sort_key,
    build_articles_from_chunks,
    query_candidates_for_article,
)


# ── Text helpers ─────────────────────────────────────────────────────

def shorten(text: str, max_len: int = 240) -> str:
    text = normalize_ws(text)
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + '...'


def diff_excerpt(text: str, start: int, end: int, window: int = 120) -> str:
    left = max(0, start - window)
    right = min(len(text), end + window)
    return shorten(text[left:right].strip(), max_len=300)


def _split_lines(text: str | None) -> list[str]:
    if not text:
        return []
    return str(text).splitlines()


def build_diff_blocks(
    before_text: str | None,
    after_text: str | None,
    max_text_len: int = 900,
) -> list[dict]:
    """Build deterministic line-level diff blocks for LLM annotation and UI."""
    before_lines = _split_lines(before_text)
    after_lines = _split_lines(after_text)
    matcher = difflib.SequenceMatcher(None, before_lines, after_lines)
    blocks = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            continue
        before_block = "\n".join(before_lines[i1:i2]).strip()
        after_block = "\n".join(after_lines[j1:j2]).strip()
        if tag == 'delete':
            block_tag = 'removed'
        elif tag == 'insert':
            block_tag = 'added'
        else:
            block_tag = 'changed'
        blocks.append({
            'block_id': f"B{len(blocks) + 1}",
            'tag': block_tag,
            'v1_lines': list(range(i1 + 1, i2 + 1)),
            'v2_lines': list(range(j1 + 1, j2 + 1)),
            'before': shorten(before_block, max_text_len),
            'after': shorten(after_block, max_text_len),
        })

    return blocks


# ── Evidence extraction ──────────────────────────────────────────────

def extract_evidence(
    before_text: str | None, after_text: str | None, max_items: int = 3,
) -> list[dict]:
    before_norm = normalize_ws(before_text or '')
    after_norm = normalize_ws(after_text or '')

    if before_norm and not after_norm:
        return [{'tag': 'removed', 'before': shorten(before_norm, 300), 'after': ''}]
    if after_norm and not before_norm:
        return [{'tag': 'added', 'before': '', 'after': shorten(after_norm, 300)}]

    matcher = difflib.SequenceMatcher(None, before_norm, after_norm)
    evidence = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            continue
        evidence.append({
            'tag': 'changed' if tag == 'replace' else tag,
            'before': diff_excerpt(before_norm, i1, i2),
            'after': diff_excerpt(after_norm, j1, j2),
        })
        if len(evidence) >= max_items:
            break
    return evidence


def parse_first_json_object(text: str) -> dict | None:
    if not text:
        return None
    raw = text.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    match = re.search(r'\{[\s\S]*\}', raw)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


# ── Grounding policy ─────────────────────────────────────────────────

def _status_from_texts(before_norm: str, after_norm: str) -> str:
    if before_norm == after_norm:
        return 'unchanged'
    if before_norm and after_norm:
        return 'changed'
    if before_norm and not after_norm:
        return 'removed'
    return 'added'


def _normalize_evidence_items(evidence: list[dict], max_items: int = 3) -> list[dict]:
    normalized = []
    for item in evidence or []:
        if not isinstance(item, dict):
            continue
        before_part = shorten(str(item.get('before') or ''), 300)
        after_part = shorten(str(item.get('after') or ''), 300)
        if not before_part and not after_part:
            continue
        normalized.append({
            'tag': str(item.get('tag') or 'changed'),
            'before': before_part,
            'after': after_part,
        })
        if len(normalized) >= max_items:
            break
    return normalized


def _normalize_diff_annotations(
    annotations: list[dict], diff_blocks: list[dict], max_items: int = 8,
) -> list[dict]:
    blocks_by_id = {block['block_id']: block for block in diff_blocks}
    normalized = []
    for item in annotations or []:
        if not isinstance(item, dict):
            continue
        block_id = str(item.get('block_id') or '').strip()
        block = blocks_by_id.get(block_id)
        if not block:
            continue
        summary = shorten(str(item.get('summary') or ''), 300)
        legal_effect = shorten(str(item.get('legal_effect') or ''), 400)
        severity = str(item.get('severity') or 'unknown').strip().lower()
        if severity not in {'low', 'medium', 'high', 'unknown'}:
            severity = 'unknown'
        if not summary and not legal_effect:
            continue
        normalized.append({
            'block_id': block_id,
            'tag': block.get('tag', 'changed'),
            'v1_lines': block.get('v1_lines', []),
            'v2_lines': block.get('v2_lines', []),
            'summary': summary,
            'legal_effect': legal_effect,
            'severity': severity,
        })
        if len(normalized) >= max_items:
            break
    return normalized


def enforce_no_evidence_no_conclusion(
    status: str, conclusion: str, evidence: list[dict],
    before_norm: str, after_norm: str,
):
    final_status = (
        status if status in {'unchanged', 'changed', 'added', 'removed'}
        else _status_from_texts(before_norm, after_norm)
    )
    final_evidence = _normalize_evidence_items(evidence)

    if final_status != 'unchanged' and not final_evidence:
        final_evidence = _normalize_evidence_items(
            extract_evidence(before_norm, after_norm, max_items=2), max_items=2,
        )

    if final_status == 'unchanged':
        final_conclusion = 'Khong ghi nhan khac biet ve mat van ban.'
    elif final_evidence:
        cleaned = normalize_ws(conclusion or '')
        if cleaned:
            final_conclusion = cleaned
        elif final_status == 'added':
            final_conclusion = 'Dieu khoan duoc bo sung trong v2.'
        elif final_status == 'removed':
            final_conclusion = 'Dieu khoan bi loai bo so voi v1.'
        else:
            final_conclusion = 'Dieu khoan co thay doi noi dung giua v1 va v2.'
    else:
        final_conclusion = 'Khong du bang chung de ket luan; can kiem tra thu cong.'

    grounded = bool(final_evidence) or final_status == 'unchanged'
    return final_status, final_conclusion, final_evidence, grounded


# ── LLM comparison ───────────────────────────────────────────────────

def llm_compare_article(
    article_no: str,
    title: str,
    before_text: str | None,
    after_text: str | None,
    model: str = "qwen2.5:7b-instruct-q4_K_M",
) -> dict:
    before_norm = normalize_ws(before_text or '')
    after_norm = normalize_ws(after_text or '')
    diff_blocks = [] if before_norm == after_norm else build_diff_blocks(before_text, after_text)

    if before_norm == after_norm:
        return {
            'status': 'unchanged',
            'conclusion': 'Khong ghi nhan khac biet ve mat van ban.',
            'evidence': [],
            'diff_blocks': [],
            'diff_annotations': [],
            'llm_model': None,
            'llm_used': False,
            'fallback_reason': 'texts_equal',
            'grounded': True,
        }

    prompt_diff_blocks = [
        {
            'block_id': block['block_id'],
            'tag': block['tag'],
            'v1_lines': block['v1_lines'],
            'v2_lines': block['v2_lines'],
            'before': shorten(block.get('before', ''), 600),
            'after': shorten(block.get('after', ''), 600),
        }
        for block in diff_blocks[:8]
    ]
    diff_blocks_json = json.dumps(prompt_diff_blocks, ensure_ascii=False, indent=2)

    prompt = f"""
Ban la tro ly doi chieu hop dong. So sanh 2 PHIEN BAN cua CUNG MOT DIEU.

Muc tieu:
- Xac dinh trang thai thay doi.
- Dua ra ket luan ngan gon.
- Trich dan bang chung tu chinh van ban da cho.
- Giai thich y nghia cua tung block thay doi da duoc code xac dinh san.

QUY TAC BAT BUOC:
1) Chi su dung noi dung trong 'Dieu v1' va 'Dieu v2'. Khong bo sung kien thuc ngoai.
2) Trang thai CHI duoc la mot trong: unchanged, changed, added, removed.
3) Neu khong tim thay bang chung text ro rang, evidence phai de rong va conclusion ghi ro "Khong du bang chung de ket luan".
4) diff_annotations CHI duoc tham chieu block_id co trong DIFF_BLOCKS. Khong tu tao block_id moi.
5) severity CHI duoc la low, medium, high, unknown.
6) Tra ve DUY NHAT JSON dung schema, KHONG them markdown hay giai thich.

SCHEMA JSON:
{{
  "status": "unchanged|changed|added|removed",
  "conclusion": "string",
  "evidence": [
    {{"tag": "changed|added|removed", "before": "string", "after": "string"}}
  ],
  "diff_annotations": [
    {{
      "block_id": "B1",
      "summary": "string tom tat block thay doi",
      "legal_effect": "string neu tac dong phap ly/nghia vu/quyen loi; neu khong ro thi ghi unknown",
      "severity": "low|medium|high|unknown"
    }}
  ]
}}

META:
- article_number: {article_no}
- article_title: {title}

Dieu v1:
{before_norm or '(khong co)'}

Dieu v2:
{after_norm or '(khong co)'}

DIFF_BLOCKS do he thong xac dinh san:
{diff_blocks_json}
""".strip()

    if ollama is None:
        status, conclusion, evidence, grounded = enforce_no_evidence_no_conclusion(
            _status_from_texts(before_norm, after_norm),
            'Khong goi duoc LLM (missing ollama package).',
            extract_evidence(before_norm, after_norm, max_items=2),
            before_norm, after_norm,
        )
        return {
            'status': status, 'conclusion': conclusion, 'evidence': evidence,
            'diff_blocks': diff_blocks, 'diff_annotations': [],
            'llm_model': None, 'llm_used': False,
            'fallback_reason': 'missing_ollama_package', 'grounded': grounded,
        }

    try:
        response = ollama.chat(
            model=model,
            messages=[{'role': 'user', 'content': prompt}],
            options={'temperature': 0},
        )
        content = (response.get('message') or {}).get('content', '')
        parsed = parse_first_json_object(content)
        if not parsed:
            raise ValueError('LLM output is not valid JSON')

        status = parsed.get('status')
        conclusion = parsed.get('conclusion') or ''
        evidence = parsed.get('evidence') if isinstance(parsed.get('evidence'), list) else []
        annotations = (
            parsed.get('diff_annotations')
            if isinstance(parsed.get('diff_annotations'), list) else []
        )

        status, conclusion, evidence, grounded = enforce_no_evidence_no_conclusion(
            status, conclusion, evidence, before_norm, after_norm,
        )
        diff_annotations = _normalize_diff_annotations(annotations, diff_blocks)
        return {
            'status': status, 'conclusion': conclusion, 'evidence': evidence,
            'diff_blocks': diff_blocks, 'diff_annotations': diff_annotations,
            'llm_model': model, 'llm_used': True,
            'fallback_reason': None, 'grounded': grounded,
        }
    except Exception as exc:
        status, conclusion, evidence, grounded = enforce_no_evidence_no_conclusion(
            _status_from_texts(before_norm, after_norm),
            f'LLM fail ({type(exc).__name__}), fallback rule-based.',
            extract_evidence(before_norm, after_norm, max_items=2),
            before_norm, after_norm,
        )
        return {
            'status': status, 'conclusion': conclusion, 'evidence': evidence,
            'diff_blocks': diff_blocks, 'diff_annotations': [],
            'llm_model': model, 'llm_used': False,
            'fallback_reason': str(exc), 'grounded': grounded,
        }


# ── Full comparison with vector retrieval ────────────────────────────

def compare_articles_with_vector_retrieval(
    chunks_v1: list[dict],
    chunks_v2: list[dict],
    chroma_dir: Path | str,
    embedder,
    llm_model: str = "qwen2.5:7b-instruct-q4_K_M",
    collection_name: str = "legal_chunks",
    top_k: int = 3,
    threshold: float = 0.50,
) -> list[dict]:
    """Compare two sets of chunks using vector retrieval + LLM."""
    left_articles = build_articles_from_chunks(chunks_v1)
    right_articles = build_articles_from_chunks(chunks_v2)

    left_numbers = sorted(left_articles.keys(), key=article_sort_key)
    matched_right = set()
    results = []

    for article_no in left_numbers:
        left = left_articles[article_no]
        candidates = query_candidates_for_article(
            left['full_text'], target_version='v2',
            chroma_dir=chroma_dir, embedder=embedder,
            collection_name=collection_name, top_k=top_k,
        )

        chosen = None
        for cand in candidates:
            cand_article_no = cand.get('article_number')
            if not cand_article_no or cand_article_no in matched_right:
                continue
            if cand['similarity'] >= threshold:
                chosen = cand
                break

        if chosen is None:
            llm_result = llm_compare_article(
                article_no=article_no,
                title=left['article_title'],
                before_text=left['full_text'],
                after_text=None,
                model=llm_model,
            )
            results.append({
                'article_number': article_no,
                'article_title': left['article_title'],
                'matched_article_v2': None,
                'match_score': 0.0,
                **llm_result,
                'v1_text': left['full_text'],
                'v2_text': None,
            })
            continue

        matched_article_no = chosen['article_number']
        matched_right.add(matched_article_no)
        right = right_articles.get(matched_article_no)
        right_text = right['full_text'] if right else chosen['text']
        title = (right or {}).get(
            'article_title', chosen.get('article_title') or left['article_title'],
        )

        llm_result = llm_compare_article(
            article_no=article_no, title=title,
            before_text=left['full_text'], after_text=right_text,
            model=llm_model,
        )
        results.append({
            'article_number': article_no,
            'article_title': title,
            'matched_article_v2': matched_article_no,
            'match_score': round(float(chosen['similarity']), 4),
            **llm_result,
            'v1_text': left['full_text'],
            'v2_text': right_text,
        })

    # Articles only in v2 (added)
    for article_no in sorted(right_articles.keys(), key=article_sort_key):
        if article_no in matched_right:
            continue
        right = right_articles[article_no]
        llm_result = llm_compare_article(
            article_no=article_no,
            title=right['article_title'],
            before_text=None,
            after_text=right['full_text'],
            model=llm_model,
        )
        results.append({
            'article_number': article_no,
            'article_title': right['article_title'],
            'matched_article_v2': article_no,
            'match_score': 0.0,
            **llm_result,
            'v1_text': None,
            'v2_text': right['full_text'],
        })

    return results
