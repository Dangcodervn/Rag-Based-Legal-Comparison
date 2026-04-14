"""Embedding and ChromaDB indexing for legal chunks."""

from pathlib import Path

from sentence_transformers import SentenceTransformer
from pyvi import ViTokenizer
import chromadb


def load_embedder(model_name: str, hf_token: str | None = None):
    """Load a SentenceTransformer embedding model."""
    return SentenceTransformer(model_name, token=hf_token)


def get_collection(chroma_dir: Path | str, collection_name: str = "legal_chunks"):
    """Get or create a ChromaDB collection."""
    client = chromadb.PersistentClient(path=str(chroma_dir))
    return client.get_or_create_collection(collection_name)


def embed_chunks(chunks: list[dict], embedder) -> list[list[float]]:
    """Embed chunk texts using ViTokenizer segmentation + embedder."""
    texts = [c["text"] for c in chunks]
    segmented = [ViTokenizer.tokenize(t) for t in texts]
    vectors = embedder.encode(segmented, convert_to_numpy=True, show_progress_bar=True)
    return [v.tolist() for v in vectors]


def index_chunks(
    chunks: list[dict],
    chroma_dir: Path | str,
    embedder,
    collection_name: str = "legal_chunks",
    batch_size: int = 64,
) -> int:
    """Embed and upsert chunks into ChromaDB. Returns count indexed."""
    if not chunks:
        return 0
    collection = get_collection(chroma_dir, collection_name)
    vectors = embed_chunks(chunks, embedder)
    for start in range(0, len(chunks), batch_size):
        end = min(start + batch_size, len(chunks))
        batch = chunks[start:end]
        collection.upsert(
            ids=[c["chunk_id"] for c in batch],
            documents=[c["text"] for c in batch],
            metadatas=[
                {
                    "doc_id": c["doc_id"],
                    "version": c["version"],
                    "chuong_so": c["chuong_so"],
                    "muc_so": c["muc_so"],
                    "article_number": c["article_number"],
                    "article_title": c["article_title"],
                    "khoan_count": c["khoan_count"],
                    "diem_count": c["diem_count"],
                    "tieu_muc_count": c.get("tieu_muc_count", 0),
                }
                for c in batch
            ],
            embeddings=vectors[start:end],
        )
    return len(chunks)


def build_index(
    chunks: list[dict],
    chroma_dir: Path | str,
    embedder,
    collection_name: str = "legal_chunks",
) -> int:
    """Convenience wrapper: embed + index chunks. Returns count."""
    return index_chunks(chunks, chroma_dir, embedder, collection_name)
