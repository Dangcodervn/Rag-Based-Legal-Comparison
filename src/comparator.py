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

# Minimum difflib text-similarity ratio for a P2 (exact-number) match to be
# accepted.  When V1 and V2 share the same article number but body content is
# fundamentally different (e.g. an article was replaced), the ratio will be
# very low and P2 is rejected so P3 (hybrid BM25+Cosine) can find a better
# semantic match — or correctly mark the clause as removed/added.
P2_MIN_TEXT_SIMILARITY = 0.40

# ── Article-level (Điều) anchoring ───────────────────────────────────
# Before matching at the Khoản level, each V1 Điều is anchored to at most one
# V2 Điều using whole-article (title + concatenated khoản body) similarity.
# Khoản matching is then constrained to anchored Điều pairs so that a V1 khoản
# whose Điều was deleted in V2 cannot "steal" a similar-looking khoản slot in a
# *different* V2 Điều (cross-article contamination). A V1 Điều with no
# acceptable anchor → all of its khoản are deterministically marked removed.
ANCHOR_MIN_SCORE    = 0.30   # minimum combined title+body score to anchor
ANCHOR_TITLE_WEIGHT = 0.40
ANCHOR_BODY_WEIGHT  = 0.60
ANCHOR_SAME_NUMBER_BONUS = 0.05  # small prior for keeping the same Điều number


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


# Leading clause-number prefix like '9.1.', '10.4.', '9.', 'a)', '1)'.
_CLAUSE_PREFIX_RE = re.compile(r'^\s*(?:\d+(?:\.\d+)*\.?|[a-zđ]\)|\(\d+\)|\d+\))\s*')


def _compare_key(body_text: str) -> str:
    """Normalise body text for equality comparison only (not for display).

    Strips the leading clause-number prefix so that a clause whose only change
    is renumbering (e.g. '9.1. ...' in V1 vs '8.1. ...' in V2, same body) is
    correctly detected as *unchanged* instead of being sent to the LLM as a
    false 'changed'. The original text is kept intact for display / evidence.
    """
    text = normalize_ws(body_text or '')
    return _CLAUSE_PREFIX_RE.sub('', text).strip()


def _dieu_aggregate(articles: dict) -> dict[str, dict]:
    """Group khoản-level articles by ``dieu_number`` into per-Điều aggregates.

    Each entry concatenates the body text of every khoản belonging to the Điều
    so that article-level anchoring can compare whole Điều against whole Điều.

    Returns ``{dieu_number: {'title': str, 'body': str, 'members': [no, ...]}}``.
    """
    agg: dict[str, dict] = {}
    for no, art in articles.items():
        dieu = str(art.get('dieu_number') or no)
        body = normalize_ws(_body_text(art.get('full_text', ''), art.get('article_title', '')))
        if dieu not in agg:
            agg[dieu] = {
                'title':   normalize_ws(art.get('article_title', '')),
                'bodies':  [],
                'members': [],
            }
        if body:
            agg[dieu]['bodies'].append(body)
        agg[dieu]['members'].append(no)
    for d in agg.values():
        d['body'] = ' '.join(d['bodies'])
    return agg


def _anchor_dieu(left_articles: dict, right_articles: dict) -> dict[str, str | None]:
    """Compute a 1:1 anchor mapping V1 Điều → V2 Điều.

    Every V1 Điều is matched to at most one V2 Điều by combined title+body
    similarity, assigned greedily highest-score-first so each V2 Điều is used
    once. A V1 Điều whose best partner scores below ``ANCHOR_MIN_SCORE`` (or is
    already taken) maps to ``None``, marking the whole article — and all of its
    khoản — as removed. This prevents cross-article khoản contamination.
    """
    left_agg  = _dieu_aggregate(left_articles)
    right_agg = _dieu_aggregate(right_articles)

    scored: list[tuple[float, str, str]] = []
    for l_dieu, l in left_agg.items():
        l_title_u = l['title'].upper()
        l_body    = l['body']
        for r_dieu, r in right_agg.items():
            title_ratio = (
                difflib.SequenceMatcher(None, l_title_u, r['title'].upper()).ratio()
                if (l_title_u or r['title']) else 0.0
            )
            body_ratio = (
                difflib.SequenceMatcher(None, l_body, r['body']).ratio()
                if (l_body or r['body']) else 0.0
            )
            score = ANCHOR_TITLE_WEIGHT * title_ratio + ANCHOR_BODY_WEIGHT * body_ratio
            if l_dieu == r_dieu:
                score += ANCHOR_SAME_NUMBER_BONUS
            scored.append((score, l_dieu, r_dieu))

    scored.sort(key=lambda x: x[0], reverse=True)
    anchor: dict[str, str | None] = {d: None for d in left_agg}
    used_right: set[str] = set()
    for score, l_dieu, r_dieu in scored:
        if score < ANCHOR_MIN_SCORE:
            break
        if anchor[l_dieu] is not None or r_dieu in used_right:
            continue
        anchor[l_dieu] = r_dieu
        used_right.add(r_dieu)
    return anchor


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

    # ── Step 0: article-level (Điều) anchoring ───────────────────────
    # Anchor each V1 Điều to at most one V2 Điều so that Khoản matching below is
    # constrained to anchored Điều pairs. dieu_anchor[v1_dieu] is the V2 Điều
    # number (or None → the whole Điều, and all its khoản, is removed).
    dieu_anchor = _anchor_dieu(left_articles, right_articles)
    right_dieu_of = {
        no: str(art.get('dieu_number') or no) for no, art in right_articles.items()
    }

    def _anchored_v2_dieu(art: dict, composite_no: str) -> str | None:
        return dieu_anchor.get(str(art.get('dieu_number') or composite_no))

    # ── Opt 1: single ChromaDB connection ────────────────────────────
    collection = get_collection(chroma_dir, collection_name)

    # ── Opt 2: batch-embed articles that need vector search ──────────
    # P2 (exact key match) is only accepted when body-text similarity ≥
    # P2_MIN_TEXT_SIMILARITY.  Pre-compute which P2 candidates are valid so
    # that rejected ones are included in needs_vector for P3.
    p2_valid: set[str] = set()
    for _no in left_numbers:
        if _no in right_articles:
            # Anchor guard: an exact composite-key match is only valid when the
            # V1 Điều is anchored to the V2 Điều that this key belongs to.
            if _anchored_v2_dieu(left_articles[_no], _no) != right_dieu_of.get(_no):
                continue
            _lbody = normalize_ws(_body_text(
                left_articles[_no]['full_text'],
                left_articles[_no].get('article_title', ''),
            ))
            _rbody = normalize_ws(_body_text(
                right_articles[_no]['full_text'],
                right_articles[_no].get('article_title', ''),
            ))
            ratio = difflib.SequenceMatcher(None, _lbody, _rbody).ratio()
            if ratio >= P2_MIN_TEXT_SIMILARITY:
                p2_valid.add(_no)

    def _needs_vector_search(no: str) -> bool:
        # Need vector search when no P2 valid match exists.
        return no not in p2_valid

    needs_vector = [no for no in left_numbers if _needs_vector_search(no)]
    pre_embeddings: dict[str, list[float]] = {}
    if needs_vector:
        texts = [
            ViTokenizer.tokenize(normalize_ws(
                _body_text(left_articles[no]['full_text'], left_articles[no].get('article_title', ''))
            ))
            for no in needs_vector
        ]
        vecs = embedder.encode(
            texts, convert_to_numpy=True, show_progress_bar=False,
            normalize_embeddings=True,
        )
        pre_embeddings = {no: vecs[i].tolist() for i, no in enumerate(needs_vector)}

    # ── Pass 1: resolve all pairs, collect LLM tasks ─────────────────
    def _reserve_task_key(base: str) -> str:
        """Create a collision-free internal key for llm_tasks/result_order."""
        if base not in llm_tasks and base not in resolved:
            return base
        i = 1
        while True:
            candidate = f"{base}__v2_only_{i}"
            if candidate not in llm_tasks and candidate not in resolved:
                return candidate
            i += 1

    result_order: list[str] = []
    resolved:  dict[str, dict] = {}   # results that don't need LLM
    llm_tasks: dict[str, dict] = {}   # tasks that need LLM

    for article_no in left_numbers:
        left = left_articles[article_no]
        result_order.append(article_no)

        chosen = None
        # Priority 2: Điều-number exact match — only when body texts are
        # semantically similar enough (ratio ≥ P2_MIN_TEXT_SIMILARITY).
        if article_no in p2_valid and article_no not in matched_right:
            right_same = right_articles[article_no]
            chosen = {
                'article_number': article_no,
                'article_title':  right_same['article_title'],
                'text':           right_same['full_text'],
                'similarity':     1.0,
            }

        # Priority 3: hybrid BM25+Cosine (uses pre-computed embedding)
        # Constrained to the V2 Điều this V1 Điều is anchored to (Step 0). When
        # the V1 Điều has no anchor (anchored_v2_dieu is None) every candidate
        # is rejected, so the khoản falls through to removed.
        anchored_v2_dieu = _anchored_v2_dieu(left, article_no)
        if chosen is None and anchored_v2_dieu is not None and article_no in pre_embeddings:
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
                and right_dieu_of.get(n) == anchored_v2_dieu
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

        # No match → removed (v1-only). Deterministic, no LLM needed: a clause
        # with no counterpart in V2 is unambiguously removed.
        if chosen is None:
            before_full = left['full_text']
            before_norm_full = normalize_ws(_body_text(before_full, left.get('article_title', '')))
            resolved[article_no] = {
                'article_number':     article_no,
                'dieu_number':        left.get('dieu_number', article_no),
                'khoan_number':       left.get('khoan_number', '0'),
                'clause_id':          left.get('clause_id', ''),
                'article_title':      left['article_title'],
                'matched_article_v2': None,
                'match_score':        0.0,
                'status':             'removed',
                'conclusion':         'Dieu khoan bi loai bo so voi v1.',
                'evidence':           _normalize_evidence_items(
                    extract_evidence(before_norm_full, '', max_items=2), max_items=2,
                ),
                'diff_blocks':        build_diff_blocks(before_full, None),
                'llm_model':          None,
                'llm_used':           False,
                'fallback_reason':    'no_match_removed',
                'grounded':           True,
                'v2_only':            False,
                'v1_text':            before_full,
                'v2_text':            '',
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
        # Compare with clause-number prefixes stripped so that a pure
        # renumbering (e.g. '9.1.'→'8.1.') with identical body is unchanged.
        if _compare_key(before_body) == _compare_key(after_body):
            resolved[article_no] = {
                'article_number':     article_no,
                'dieu_number':        left.get('dieu_number', article_no),
                'khoan_number':       left.get('khoan_number', '0'),
                'clause_id':          left.get('clause_id', ''),
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
            'clause_id':    left.get('clause_id', ''),
            'v2_only':      False,
        }

    # Articles only in v2 (added). Deterministic, no LLM needed: a clause with
    # no counterpart in V1 is unambiguously added.
    for article_no in sorted(right_articles.keys(), key=article_sort_key):
        if article_no in matched_right:
            continue
        right = right_articles[article_no]
        result_key = _reserve_task_key(article_no)
        result_order.append(result_key)
        after_full = right['full_text']
        after_norm_full = normalize_ws(_body_text(after_full, right.get('article_title', '')))
        resolved[result_key] = {
            'article_number':     article_no,
            'dieu_number':        right.get('dieu_number', article_no),
            'khoan_number':       right.get('khoan_number', '0'),
            'clause_id':          right.get('clause_id', ''),
            'article_title':      right['article_title'],
            'matched_article_v2': article_no,
            'match_score':        0.0,
            'status':             'added',
            'conclusion':         'Dieu khoan duoc bo sung trong v2.',
            'evidence':           _normalize_evidence_items(
                extract_evidence('', after_norm_full, max_items=2), max_items=2,
            ),
            'diff_blocks':        build_diff_blocks(None, after_full),
            'llm_model':          None,
            'llm_used':           False,
            'fallback_reason':    'v2_only_added',
            'grounded':           True,
            'v2_only':            True,
            'v1_text':            '',
            'v2_text':            after_full,
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
    for task_key in result_order:
        if task_key in resolved:
            results.append(resolved[task_key])
            continue
        t     = llm_tasks[task_key]
        llm_r = llm_results[task_key]
        results.append({
            'article_number':     t['article_no'],
            'dieu_number':        t['dieu_number'],
            'khoan_number':       t['khoan_number'],
            'clause_id':          t.get('clause_id', ''),
            'article_title':      t['title'],
            'matched_article_v2': t['matched_no'],
            'match_score':        round(float(t['similarity']), 4),
            'v2_only':            t.get('v2_only', False),
            **llm_r,
            # Use full texts (with heading) for display/side-by-side viewer
            'v1_text': t.get('v1_text_full', t['before']),
            'v2_text': t.get('v2_text_full', t['after']),
        })

    return results
