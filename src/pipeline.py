"""End-to-end comparison pipeline: files → report."""

import os
from pathlib import Path
from typing import Callable

from loguru import logger

from src.ingest import read_and_normalize
from src.chunker import chunk_document, explode_to_khoan_chunks
from src.indexer import load_embedder, index_chunks, embed_chunks, reset_collection
from src.comparator import compare_articles_with_vector_retrieval
from src.reporter import (
    build_report,
    build_summary_df,
    build_citation_df,
    save_report_json,
    build_copilot_report,
    render_copilot_text,
    save_copilot_report_json,
    save_copilot_report_txt,
)

from configs.defaults import (
    EMBEDDING_MODEL,
    CHROMA_COLLECTION,
    OLLAMA_MODEL,
    COSINE_LOW,
)


def _is_preamble_item(item: dict) -> bool:
    """Return True when a comparison row belongs to synthetic preamble Điều 0."""
    dieu = str(item.get('dieu_number') or item.get('article_number') or '').strip().upper()
    return dieu == '0'


def _is_synthetic_section_item(item: dict) -> bool:
    """Return True for auto-generated unnumbered sections (S1, S2, ...)."""
    dieu = str(item.get('dieu_number') or item.get('article_number') or '').strip().upper()
    return dieu.startswith('S') and dieu[1:].isdigit()


def _is_non_khoan_item(item: dict) -> bool:
    """Return True for rows that are not clause-level (Khoan 0 / missing)."""
    khoan = str(item.get('khoan_number') or '0').strip()
    return khoan == '0'


def run_comparison_pipeline(
    file_v1: Path,
    file_v2: Path,
    chroma_dir: Path,
    output_dir: Path,
    llm_model: str = OLLAMA_MODEL,
    embed_model: str = EMBEDDING_MODEL,
    collection_name: str = CHROMA_COLLECTION,
    top_k: int = 3,
    threshold: float = COSINE_LOW,
    hf_token: str | None = None,
    include_preamble: bool = False,
    include_non_khoan: bool = False,
    on_progress: Callable[[str, float], None] | None = None,
    embedder=None,
) -> dict:
    """
    Full pipeline: 2 files → comparison report.

    Args:
        file_v1: Path to version 1 document (DOCX/PDF).
        file_v2: Path to version 2 document (DOCX/PDF).
        chroma_dir: Directory for ChromaDB persistent storage.
        output_dir: Directory to save report JSON.
        llm_model: Ollama model name for comparison.
        embed_model: SentenceTransformer model name.
        collection_name: ChromaDB collection name.
        top_k: Number of vector candidates to retrieve.
        threshold: Minimum similarity score for matching.
        hf_token: HuggingFace token (optional).
        include_preamble: Include Điều 0 rows in report outputs.
        include_non_khoan: Include non-clause rows (S* sections, Khoan 0).
        on_progress: Callback(step_name, progress_fraction) for UI.
        embedder: Pre-loaded SentenceTransformer instance. When provided,
                  the pipeline skips the model-loading step entirely.

    Returns:
        Dict with keys: report, summary_df, citation_df, report_path.
    """
    def _progress(step: str, frac: float):
        logger.info(f"[{frac:.0%}] {step}")
        if on_progress:
            on_progress(step, frac)

    # ── Step 1: Read & normalize ─────────────────────────────────────
    _progress("Doc va chuan hoa file v1...", 0.0)
    doc_v1 = read_and_normalize(file_v1)

    _progress("Doc va chuan hoa file v2...", 0.10)
    doc_v2 = read_and_normalize(file_v2)

    # ── Step 2: Chunk ────────────────────────────────────────────────
    _progress("Chia chunk v1 theo Dieu...", 0.20)
    chunks_v1 = chunk_document(doc_v1, doc_id=file_v1.stem, version='v1')

    _progress("Chia chunk v2 theo Dieu...", 0.25)
    chunks_v2 = chunk_document(doc_v2, doc_id=file_v2.stem, version='v2')

    _progress("Tach chunk theo Khoan...", 0.28)
    chunks_v1 = explode_to_khoan_chunks(chunks_v1)
    chunks_v2 = explode_to_khoan_chunks(chunks_v2)

    logger.info(f"Khoan chunks: v1={len(chunks_v1)}, v2={len(chunks_v2)}")

    # ── Step 3: Embed & index ────────────────────────────────────────
    if embedder is None:
        _progress("Tai embedding model...", 0.30)
        hf_token = hf_token or os.getenv('HF_TOKEN')
        embedder = load_embedder(embed_model, hf_token=hf_token)
    else:
        _progress("Embedding model san sang...", 0.30)

    # Clear stale vectors from previous comparison runs to avoid cross-contamination
    reset_collection(chroma_dir, collection_name)

    _progress("Index v1 vao ChromaDB...", 0.40)
    n1 = index_chunks(chunks_v1, chroma_dir, embedder, collection_name)

    _progress("Index v2 vao ChromaDB...", 0.50)
    n2 = index_chunks(chunks_v2, chroma_dir, embedder, collection_name)

    logger.info(f"Indexed: v1={n1}, v2={n2}")

    # ── Step 4: Compare ──────────────────────────────────────────────
    _progress("So sanh cac Dieu bang vector retrieval + LLM...", 0.60)
    comparison_results = compare_articles_with_vector_retrieval(
        chunks_v1=chunks_v1,
        chunks_v2=chunks_v2,
        chroma_dir=chroma_dir,
        embedder=embedder,
        llm_model=llm_model,
        collection_name=collection_name,
        top_k=top_k,
        threshold=threshold,
    )

    # Keep raw internals unchanged, but return clause-level rows by default.
    report_results = comparison_results
    if not include_preamble:
        report_results = [r for r in report_results if not _is_preamble_item(r)]
    if not include_non_khoan:
        report_results = [
            r for r in report_results
            if not _is_synthetic_section_item(r) and not _is_non_khoan_item(r)
        ]
    logger.info(
        "Filtered output rows: {} -> {} (include_preamble={}, include_non_khoan={})",
        len(comparison_results),
        len(report_results),
        include_preamble,
        include_non_khoan,
    )

    # ── Step 5: Report ───────────────────────────────────────────────
    _progress("Tao bao cao...", 0.90)
    config = {
        'file_v1': file_v1.name,
        'file_v2': file_v2.name,
        'llm_model': llm_model,
        'embed_model': embed_model,
        'vector_top_k': top_k,
        'vector_match_threshold': threshold,
    }

    report = build_report(report_results, config)
    summary_df = build_summary_df(report_results)
    citation_df = build_citation_df(report_results)
    copilot_report = build_copilot_report(report, max_items=20)
    copilot_text = render_copilot_text(copilot_report)

    output_dir.mkdir(parents=True, exist_ok=True)
    report_filename = f"{file_v1.stem}_vs_{file_v2.stem}_report.json"
    report_path = save_report_json(report, output_dir / report_filename)
    copilot_json_path = save_copilot_report_json(
        copilot_report,
        output_dir / f"{file_v1.stem}_vs_{file_v2.stem}_copilot.json",
    )
    copilot_txt_path = save_copilot_report_txt(
        copilot_text,
        output_dir / f"{file_v1.stem}_vs_{file_v2.stem}_copilot.txt",
    )

    _progress("Hoan tat!", 1.0)
    logger.info(f"Report saved: {report_path}")
    logger.info(f"Copilot compact JSON: {copilot_json_path}")
    logger.info(f"Copilot summary text: {copilot_txt_path}")
    logger.info("\n" + copilot_text)

    return {
        'report': report,
        'summary_df': summary_df,
        'citation_df': citation_df,
        'report_path': report_path,
        'copilot_report': copilot_report,
        'copilot_text': copilot_text,
        'copilot_json_path': copilot_json_path,
        'copilot_txt_path': copilot_txt_path,
        'chunks_v1': chunks_v1,
        'chunks_v2': chunks_v2,
    }
