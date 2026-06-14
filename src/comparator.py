"""LLM-based article comparison with evidence grounding."""

import difflib
import json
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

try:
    import ollama
except ImportError:
    ollama = None

try:
    from rank_bm25 import BM25Okapi
except ImportError:
    BM25Okapi = None

from src.ingest import normalize_ws
from src.indexer import get_collection
from src.retriever import (
    article_sort_key,
    build_articles_from_chunks,
    query_with_vector,
)
from configs.defaults import COSINE_LOW, COSINE_HIGH

COSINE_WEIGHT = 0.70
BM25_WEIGHT   = 0.30


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

def _parse_composite_no(article_no: str) -> tuple[str, str]:
    """Split composite '1.2' → ('1', '2'); '1' → ('1', '0')."""
    if '.' in article_no:
        parts = article_no.split('.', 1)
        return parts[0], parts[1]
    return article_no, '0'


def llm_compare_article(
    article_no: str,
    title: str,
    before_text: str | None,
    after_text: str | None,
    model: str = "qwen2.5:7b-instruct-q4_K_M",
    match_type: str = "matched",
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
            'llm_model': None,
            'llm_used': False,
            'fallback_reason': 'texts_equal',
            'grounded': True,
        }

    dieu_no, khoan_no = _parse_composite_no(article_no)
    weak_hint = (
        '\nCHU Y: Cap nay co do tuong dong thap; co the khong cung khoan.'
        if match_type == 'weak_match' else ''
    )
    meta = (
        f"Dieu {dieu_no} - {title} | Khoan {khoan_no}"
        if khoan_no != '0'
        else f"Dieu {dieu_no} - {title}"
    )

    prompt = f"""Ban la tro ly doi chieu van ban phap ly. So sanh 2 phien ban cung mot Khoan.{weak_hint}
YEU CAU NGON NGU: Viet tat ca noi dung trong truong "conclusion" bang TIENG VIET. Khong dung tieng Anh hay tieng Trung trong conclusion.

QUY TAC BAT BUOC:
1. Chi dung noi dung trong "Khoan v1" va "Khoan v2". Khong bo sung kien thuc ngoai.
2. Trang thai CHI duoc la: unchanged | changed | added | removed.
3. Neu khong co bang chung text ro rang, evidence phai de rong va conclusion ghi ro "Khong du bang chung de ket luan".
4. Tra ve DUY NHAT JSON hop le, KHONG them markdown hay giai thich.
5. Truong "conclusion" PHAI viet bang tieng Viet co dau.

SCHEMA:
{{"status":"unchanged|changed|added|removed","conclusion":"<tieng Viet>","evidence":[{{"tag":"changed|added|removed","before":"string","after":"string"}}]}}

META: {meta}

Khoan v1:
{before_norm or '(khong co)'}

Khoan v2:
{after_norm or '(khong co)'}""".strip()

    if ollama is None:
        status, conclusion, evidence, grounded = enforce_no_evidence_no_conclusion(
            _status_from_texts(before_norm, after_norm),
            'Khong goi duoc LLM (missing ollama package).',
            extract_evidence(before_norm, after_norm, max_items=2),
            before_norm, after_norm,
        )
        return {
            'status': status, 'conclusion': conclusion, 'evidence': evidence,
            'diff_blocks': diff_blocks,
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

        status, conclusion, evidence, grounded = enforce_no_evidence_no_conclusion(
            status, conclusion, evidence, before_norm, after_norm,
        )
        return {
            'status': status, 'conclusion': conclusion, 'evidence': evidence,
            'diff_blocks': diff_blocks,
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
            'diff_blocks': diff_blocks,
            'llm_model': model, 'llm_used': False,
            'fallback_reason': str(exc), 'grounded': grounded,
        }


# ── Full comparison with vector retrieval ────────────────────────────

def _tokenize_vi(text: str) -> list[str]:
    """Simple whitespace tokenizer for BM25 (Vietnamese-safe)."""
    return normalize_ws(text).lower().split()


def _build_bm25_index(articles: dict[str, dict]):
    """Build BM25 index over article texts. Returns (corpus_keys, bm25 | None)."""
    keys = list(articles.keys())
    if not keys or BM25Okapi is None:
        return keys, None
    tokenized = [_tokenize_vi(articles[k]['full_text']) for k in keys]
    bm25 = BM25Okapi(tokenized)
    return keys, bm25


def _hybrid_score(cosine: float, bm25_norm: float) -> float:
    return COSINE_WEIGHT * cosine + BM25_WEIGHT * bm25_norm


def _body_text(full_text: str, article_title: str) -> str:
    """Strip the heading line from article text before comparison / embedding.

    DOCX chunks include the heading as the first line, e.g.:
      '8. BỒI THƯỜNG\n<body...>'
    When a section is deleted before this one in V2 the number shifts to '7.',
    causing a spurious diff even though the body is identical.

    The heading line is removed when its uppercase form either equals or ends
    with the normalised article_title (handles '8. BỒI THƯỜNG' → 'BỒI THƯỜNG').
    Returns full_text unchanged when the first line doesn’t look like a heading.
    """
    if not full_text or not article_title:
        return full_text or ''
    title_norm = normalize_ws(article_title).upper().strip()
    if not title_norm:
        return full_text
    lines = full_text.split('\n', 1)
    first_norm = normalize_ws(lines[0]).upper().strip()
    if first_norm == title_norm or first_norm.endswith(title_norm):
        return lines[1].strip() if len(lines) > 1 else ''
    return full_text


def compare_articles_with_vector_retrieval(
    chunks_v1: list[dict],
    chunks_v2: list[dict],
    chroma_dir: Path | str,
    embedder,
    llm_model: str = "qwen2.5:7b-instruct-q4_K_M",
    collection_name: str = "legal_chunks",
    top_k: int = 3,
    threshold: float = COSINE_LOW,
) -> list[dict]:
    """Compare two sets of chunks using hybrid BM25+Cosine retrieval + LLM.

    Optimisations vs the naive version:
    - ChromaDB collection opened ONCE (not per query).
    - All vector-search query texts batch-embedded in a single encoder call.
    - LLM calls run in parallel with ThreadPoolExecutor(max_workers=2).
    """
    from pyvi import ViTokenizer

    left_articles  = build_articles_from_chunks(chunks_v1)
    right_articles = build_articles_from_chunks(chunks_v2)
    right_keys, bm25_index = _build_bm25_index(right_articles)
    left_numbers   = sorted(left_articles.keys(), key=article_sort_key)
    matched_right: set[str] = set()

    # ── Build title → article_no reverse index for V2 ────────────────
    # Used as Priority 1 matching to handle unnumbered sections (S1, S2...)
    # where sequential numbering breaks when sections are inserted/deleted.
    right_title_idx: dict[str, str] = {}
    for _no, _art in right_articles.items():
        _key = normalize_ws(_art.get('article_title', '')).upper().strip()
        if _key:
            right_title_idx[_key] = _no

    def _is_seq(article_no: str) -> bool:
        """True for auto-generated sequential S-numbers (unnumbered headings)."""
        return article_no.startswith('S') and article_no[1:].isdigit()

    # ── Opt 1: single ChromaDB connection ────────────────────────────
    collection = get_collection(chroma_dir, collection_name)

    # ── Opt 2: batch-embed articles that need vector search ──────────
    # S-numbered articles need vector when their title has no V2 match;
    # Điều-numbered articles need vector only when the number is absent in V2.
    def _needs_vector_search(no: str) -> bool:
        if _is_seq(no):
            title_key = normalize_ws(left_articles[no].get('article_title', '')).upper().strip()
            return title_key not in right_title_idx
        return no not in right_articles

    needs_vector = [no for no in left_numbers if _needs_vector_search(no)]
    pre_embeddings: dict[str, list[float]] = {}
    if needs_vector:
        texts = [
            ViTokenizer.tokenize(normalize_ws(
                _body_text(left_articles[no]['full_text'], left_articles[no].get('article_title', ''))
            ))
            for no in needs_vector
        ]
        vecs = embedder.encode(texts, convert_to_numpy=True, show_progress_bar=False)
        pre_embeddings = {no: vecs[i].tolist() for i, no in enumerate(needs_vector)}

    # ── Pass 1: resolve all pairs, collect LLM tasks ─────────────────
    result_order: list[str] = []
    resolved:  dict[str, dict] = {}   # results that don't need LLM
    llm_tasks: dict[str, dict] = {}   # tasks that need LLM

    for article_no in left_numbers:
        left = left_articles[article_no]
        result_order.append(article_no)

        chosen = None
        # Priority 1: Title exact match (case-insensitive, normalized).
        # Critical for unnumbered-heading documents (contracts/NDAs) where
        # sequential S-numbers shift when sections are added/removed mid-doc.
        left_title_key = normalize_ws(left.get('article_title', '')).upper().strip()
        if left_title_key:
            tm = right_title_idx.get(left_title_key)
            if tm and tm not in matched_right:
                right_same = right_articles[tm]
                chosen = {
                    'article_number': tm,
                    'article_title':  right_same['article_title'],
                    'text':           right_same['full_text'],
                    'similarity':     1.0,
                }

        # Priority 2: Điều-number exact match (skip for S-prefixed — unreliable).
        if chosen is None and not _is_seq(article_no) \
                and article_no in right_articles and article_no not in matched_right:
            right_same = right_articles[article_no]
            chosen = {
                'article_number': article_no,
                'article_title':  right_same['article_title'],
                'text':           right_same['full_text'],
                'similarity':     1.0,
            }

        # Priority 3: hybrid BM25+Cosine (uses pre-computed embedding)
        if chosen is None and article_no in pre_embeddings:
            candidates = query_with_vector(
                pre_embeddings[article_no], collection, 'v2', top_k,
            )
            cosine_by_no = {
                c['article_number']: c['similarity']
                for c in candidates if c.get('article_number')
            }
            bm25_scores_raw: dict[str, float] = {}
            if bm25_index is not None and right_keys:
                query_tokens = _tokenize_vi(left['full_text'])
                raw_scores   = bm25_index.get_scores(query_tokens)
                max_score    = max(raw_scores) if max(raw_scores) > 0 else 1.0
                bm25_scores_raw = {
                    right_keys[i]: raw_scores[i] / max_score
                    for i in range(len(right_keys))
                }
            candidate_nos = set(cosine_by_no) | set(bm25_scores_raw)
            scored = [
                (_hybrid_score(cosine_by_no.get(n, 0.0), bm25_scores_raw.get(n, 0.0)), n)
                for n in candidate_nos
                if n not in matched_right
                and _hybrid_score(cosine_by_no.get(n, 0.0), bm25_scores_raw.get(n, 0.0)) >= threshold
            ]
            scored.sort(key=lambda x: x[0], reverse=True)
            for hybrid_score, cand_no in scored:
                if cand_no not in right_articles:
                    continue
                right_cand = right_articles[cand_no]
                chosen = {
                    'article_number': cand_no,
                    'article_title':  right_cand['article_title'],
                    'text':           right_cand['full_text'],
                    'similarity':     hybrid_score,
                }
                break

        # No match → removed (v1-only)
        if chosen is None:
            llm_tasks[article_no] = {
                'article_no':   article_no,
                'title':        left['article_title'],
                'before':       left['full_text'],
                'after':        None,
                'match_type':   'no_match',
                'matched_no':   None,
                'similarity':   0.0,
                'dieu_number':  left.get('dieu_number', article_no),
                'khoan_number': left.get('khoan_number', '0'),
                'v2_only':      False,
            }
            continue

        matched_article_no = chosen['article_number']
        matched_right.add(matched_article_no)
        right      = right_articles.get(matched_article_no)
        right_text = right['full_text'] if right else chosen['text']
        title      = (right or {}).get('article_title', chosen.get('article_title') or left['article_title'])
        similarity = float(chosen.get('similarity', 0.0))

        # Strip heading lines before comparing — avoids false diffs when section
        # numbers shift (e.g. '8. BỒI THƯỜNG' in V1 vs '7. BỒI THƯỜNG' in V2).
        before_body = _body_text(left['full_text'], left.get('article_title', ''))
        after_body  = _body_text(right_text, title)
        before_norm = normalize_ws(before_body)
        after_norm  = normalize_ws(after_body)

        # Shortcut: body texts identical → unchanged, no LLM needed
        if before_norm == after_norm:
            resolved[article_no] = {
                'article_number':     article_no,
                'dieu_number':        left.get('dieu_number', article_no),
                'khoan_number':       left.get('khoan_number', '0'),
                'article_title':      title,
                'matched_article_v2': matched_article_no,
                'match_score':        round(similarity, 4),
                'status':             'unchanged',
                'conclusion':         'Khong ghi nhan khac biet ve mat van ban.',
                'evidence':           [],
                'diff_blocks':        [],
                'llm_model':          None,
                'llm_used':           False,
                'fallback_reason':    'texts_equal',
                'grounded':           True,
                'v1_text':            left['full_text'],
                'v2_text':            right_text,
            }
            continue

        match_type = 'weak_match' if similarity < COSINE_HIGH else 'matched'
        llm_tasks[article_no] = {
            'article_no':   article_no,
            'title':        title,
            'before':       before_body,   # body only — no heading number
            'after':        after_body,    # body only — no heading number
            'v1_text_full': left['full_text'],
            'v2_text_full': right_text,
            'match_type':   match_type,
            'matched_no':   matched_article_no,
            'similarity':   similarity,
            'dieu_number':  left.get('dieu_number', article_no),
            'khoan_number': left.get('khoan_number', '0'),
            'v2_only':      False,
        }

    # Articles only in v2 (added)
    for article_no in sorted(right_articles.keys(), key=article_sort_key):
        if article_no in matched_right:
            continue
        right = right_articles[article_no]
        result_order.append(article_no)
        llm_tasks[article_no] = {
            'article_no':   article_no,
            'title':        right['article_title'],
            'before':       None,
            'after':        right['full_text'],
            'match_type':   'added',
            'matched_no':   article_no,
            'similarity':   0.0,
            'dieu_number':  right.get('dieu_number', article_no),
            'khoan_number': right.get('khoan_number', '0'),
            'v2_only':      True,
        }

    # ── Opt 3: run LLM calls in parallel ─────────────────────────────
    llm_results: dict[str, dict] = {}

    def _run_llm(key: str) -> tuple[str, dict]:
        t = llm_tasks[key]
        return key, llm_compare_article(
            article_no=t['article_no'],
            title=t['title'],
            before_text=t['before'],
            after_text=t['after'],
            model=llm_model,
            match_type=t['match_type'],
        )

    # max_workers=2: Ollama processes one GPU request at a time, but 2 threads
    # keeps the queue full and overlaps Python / HTTP overhead.
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {executor.submit(_run_llm, k): k for k in llm_tasks}
        for future in as_completed(futures):
            k, llm_r = future.result()
            llm_results[k] = llm_r

    # ── Pass 3: assemble results in original order ────────────────────
    results: list[dict] = []
    for article_no in result_order:
        if article_no in resolved:
            results.append(resolved[article_no])
            continue
        t     = llm_tasks[article_no]
        llm_r = llm_results[article_no]
        results.append({
            'article_number':     article_no,
            'dieu_number':        t['dieu_number'],
            'khoan_number':       t['khoan_number'],
            'article_title':      t['title'],
            'matched_article_v2': t['matched_no'],
            'match_score':        round(float(t['similarity']), 4),
            **llm_r,
            # Use full texts (with heading) for display/side-by-side viewer
            'v1_text': t.get('v1_text_full', t['before']),
            'v2_text': t.get('v2_text_full', t['after']),
        })

    return results
