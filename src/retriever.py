"""Vector-based article retrieval from ChromaDB."""

import re
from pathlib import Path

from pyvi import ViTokenizer

from src.ingest import normalize_ws
from src.indexer import get_collection


def article_sort_key(article_no: str):
    """Sort key for article numbers, supporting composite keys like '1.10'.

    Splits on '.' and sorts each level numerically so that clause order is
    natural: 1.1, 1.2, ..., 1.9, 1.10, 1.11 (not the lexical 1.1, 1.10, 1.2).
    Numeric levels rank before non-numeric ones (e.g. synthetic sections, roman
    numerals), keeping Điều/Khoản ahead of synthetic sections.
    """
    parts = str(article_no).split('.')
    key = []
    for part in parts:
        match = re.match(r'^(\d+)([A-Za-z]*)$', part)
        if match:
            key.append((0, int(match.group(1)), match.group(2)))
        else:
            key.append((1, 0, part))
    return key


def build_articles_from_chunks(chunks: list[dict]) -> dict[str, dict]:
    """Group chunks into a dict keyed by article_number, concatenating text if multiple chunks share the same number."""
    articles = {}
    for row in chunks:
        article_no = str(row.get('article_number') or '').strip()
        if not article_no:
            continue
        if article_no not in articles:
            # Extract dieu_number, which is ALWAYS set by chunker (never None).
            # For khoan-exploded chunks: article_no='1.1', dieu_number='1'
            # For article-level chunks: article_no='1', dieu_number='1'
            # Never fallback article_no to dieu_number, as that would confuse composite keys.
            dieu_no = str(row.get('dieu_number') or '').strip()
            if not dieu_no:
                # If somehow missing, extract from article_no (split on last dot for khoan case)
                parts = article_no.rsplit('.', 1)
                dieu_no = parts[0] if len(parts) > 1 else article_no
            articles[article_no] = {
                'article_number': article_no,
                'article_title': row.get('article_title', f'Dieu {article_no}'),
                'full_text': row.get('text', ''),
                'chunk_id': row.get('chunk_id', ''),
                'clause_id': str(row.get('clause_id') or ''),
                'dieu_number': dieu_no,
                'khoan_number': str(row.get('khoan_number') or '0'),
            }
        else:
            # Concatenate text for multi-chunk articles
            extra = row.get('text', '').strip()
            if extra and extra not in articles[article_no]['full_text']:
                articles[article_no]['full_text'] += '\n' + extra
    return articles


def _distance_to_similarity(distance: float | int | None) -> float:
    if distance is None:
        return 0.0
    return 1.0 / (1.0 + float(distance))


def query_candidates_for_article(
    article_text: str,
    target_version: str,
    chroma_dir: Path | str,
    embedder,
    collection_name: str = "legal_chunks",
    top_k: int = 3,
) -> list[dict]:
    """Query ChromaDB for candidate matching articles in target_version."""
    collection = get_collection(chroma_dir, collection_name)
    query_text = ViTokenizer.tokenize(normalize_ws(article_text))
    query_vector = embedder.encode([query_text], convert_to_numpy=True)[0].tolist()

    result = collection.query(
        query_embeddings=[query_vector],
        n_results=top_k,
        where={'version': target_version},
        include=['documents', 'metadatas', 'distances'],
    )

    candidates = []
    ids = (result.get('ids') or [[]])[0]
    documents = (result.get('documents') or [[]])[0]
    metadatas = (result.get('metadatas') or [[]])[0]
    distances = (result.get('distances') or [[]])[0]

    for idx, cand_id in enumerate(ids):
        md = metadatas[idx] if idx < len(metadatas) and isinstance(metadatas[idx], dict) else {}
        distance = distances[idx] if idx < len(distances) else None
        candidates.append({
            'chunk_id': cand_id,
            'article_number': str(md.get('article_number') or ''),
            'article_title': str(md.get('article_title') or ''),
            'text': documents[idx] if idx < len(documents) else '',
            'distance': distance,
            'similarity': _distance_to_similarity(distance),
            'metadata': md,
        })
    return candidates


def query_with_vector(
    query_vector: list[float],
    collection,
    target_version: str,
    top_k: int = 3,
) -> list[dict]:
    """Query ChromaDB with a pre-computed embedding vector.

    Faster than query_candidates_for_article because it skips the per-call
    embedding and ChromaDB client creation — callers should open the collection
    once and pass it here.
    """
    result = collection.query(
        query_embeddings=[query_vector],
        n_results=top_k,
        where={'version': target_version},
        include=['documents', 'metadatas', 'distances'],
    )
    candidates = []
    ids = (result.get('ids') or [[]])[0]
    documents = (result.get('documents') or [[]])[0]
    metadatas = (result.get('metadatas') or [[]])[0]
    distances = (result.get('distances') or [[]])[0]
    for idx, cand_id in enumerate(ids):
        md = metadatas[idx] if idx < len(metadatas) and isinstance(metadatas[idx], dict) else {}
        distance = distances[idx] if idx < len(distances) else None
        candidates.append({
            'chunk_id': cand_id,
            'article_number': str(md.get('article_number') or ''),
            'article_title': str(md.get('article_title') or ''),
            'text': documents[idx] if idx < len(documents) else '',
            'distance': distance,
            'similarity': _distance_to_similarity(distance),
            'metadata': md,
        })
    return candidates
