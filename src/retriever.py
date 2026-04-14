"""Vector-based article retrieval from ChromaDB."""

import re
from pathlib import Path

from pyvi import ViTokenizer

from src.ingest import normalize_ws
from src.indexer import get_collection


def article_sort_key(article_no: str):
    """Sort key for article numbers (numeric first, then alpha suffix)."""
    text = str(article_no)
    match = re.match(r'^(\d+)([A-Za-z]*)$', text)
    if match:
        return (0, int(match.group(1)), match.group(2))
    return (1, text)


def build_articles_from_chunks(chunks: list[dict]) -> dict[str, dict]:
    """Group chunks into a dict keyed by article_number."""
    articles = {}
    for row in chunks:
        article_no = str(row.get('article_number') or '').strip()
        if not article_no:
            continue
        articles[article_no] = {
            'article_number': article_no,
            'article_title': row.get('article_title', f'Dieu {article_no}'),
            'full_text': row.get('text', ''),
            'chunk_id': row.get('chunk_id', ''),
        }
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
