"""POST /api/compare — run the full comparison pipeline."""
import asyncio
import uuid
import tempfile
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from loguru import logger  # noqa: F401  (kept for future use)

from src.pipeline import run_comparison_pipeline
from api.state import embedder_state
from api.session_store import store_session
from api.schemas import CompareResponse, ComparisonItem, EvidenceItem, ReportConfig

router = APIRouter(tags=["compare"])


@router.post("/compare", response_model=CompareResponse)
async def compare_documents(
    file_v1: UploadFile = File(...),
    file_v2: UploadFile = File(...),
    include_preamble: bool = Form(False),
    include_non_khoan: bool = Form(False),
):
    session_id = str(uuid.uuid4())
    tmp_dir = Path(tempfile.mkdtemp(prefix="legal_compare_"))
    chroma_dir = Path("chroma_db")
    output_dir = Path("outputs")

    # Use simple ASCII filenames to avoid issues with Vietnamese characters in COM paths
    ext_v1 = Path(file_v1.filename or "doc_v1.docx").suffix.lower() or ".docx"
    ext_v2 = Path(file_v2.filename or "doc_v2.docx").suffix.lower() or ".docx"
    orig_name_v1 = file_v1.filename or "doc_v1"
    orig_name_v2 = file_v2.filename or "doc_v2"
    p1 = tmp_dir / f"doc_v1{ext_v1}"
    p2 = tmp_dir / f"doc_v2{ext_v2}"
    p1.write_bytes(await file_v1.read())
    p2.write_bytes(await file_v2.read())

    embedder = embedder_state.get("embedder")

    # Run blocking pipeline in thread pool so the event loop stays free
    loop = asyncio.get_running_loop()
    try:
        result = await loop.run_in_executor(
            None,
            lambda: run_comparison_pipeline(
                file_v1=p1,
                file_v2=p2,
                chroma_dir=chroma_dir,
                output_dir=output_dir,
                embedder=embedder,
                include_preamble=include_preamble,
                include_non_khoan=include_non_khoan,
            ),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    # DOCX files are stored directly — no server-side conversion needed
    store_session(session_id, p1, p2)

    report = result["report"]
    cfg = report["config"]

    return CompareResponse(
        session_id=session_id,
        config=ReportConfig(
            file_v1=orig_name_v1,
            file_v2=orig_name_v2,
            llm_model=cfg.get("llm_model", ""),
            embed_model=cfg.get("embed_model", ""),
            total_khoans=cfg.get("total_khoans", 0),
            status_counts=cfg.get("status_counts", {}),
            grounded_count=cfg.get("grounded_count", 0),
            llm_used_count=cfg.get("llm_used_count", 0),
        ),
        results=[_map_item(i) for i in report["article_level_results"]],
        has_docx_v1=True,
        has_docx_v2=True,
    )


# ── Helpers ──────────────────────────────────────────────────────────


def _map_item(item: dict) -> ComparisonItem:
    return ComparisonItem(
        article_number=str(item.get("article_number", "")),
        dieu_number=item.get("dieu_number"),
        khoan_number=item.get("khoan_number"),
        article_title=item.get("article_title", ""),
        status=item.get("status", ""),
        match_score=float(item.get("match_score") or 0.0),
        matched_article_v2=item.get("matched_article_v2"),
        v2_only=bool(item.get("v2_only", False)),
        conclusion=item.get("conclusion", ""),
        grounded=bool(item.get("grounded")),
        llm_used=bool(item.get("llm_used")),
        evidence=[
            EvidenceItem(
                tag=e.get("tag", "changed"),
                before=e.get("before", ""),
                after=e.get("after", ""),
            )
            for e in (item.get("evidence") or [])
        ],
    )
