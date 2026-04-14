"""
Tro ly So sanh Van ban Phap ly — Streamlit UI (single-page)
Entry point: streamlit run app/streamlit_app.py
"""

import sys
import tempfile
from pathlib import Path

# Ensure project root is on sys.path
_PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import streamlit as st

from configs.defaults import (
    OLLAMA_MODEL,
    EMBEDDING_MODEL,
    CHROMA_COLLECTION,
)
from app.components.report_view import (
    render_metrics,
    render_change_list,
    render_key_summary,
    render_citations,
)

st.set_page_config(
    page_title="So sanh Van ban Phap ly",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("⚖️ Tro ly So sanh Van ban Phap ly")
st.caption("RAG + Local LLM  ·  *Khong bang chung → khong ket luan*")

# ── Validation helpers ───────────────────────────────────────────────

ALLOWED_EXTENSIONS = {'.docx', '.pdf'}
MAX_FILE_SIZE_MB = 10


def _validate_file(uploaded_file) -> str | None:
    if uploaded_file is None:
        return None
    ext = Path(uploaded_file.name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        return f"Dinh dang '{ext}' khong ho tro. Chi chap nhan DOCX hoac PDF."
    size_mb = uploaded_file.size / (1024 * 1024)
    if size_mb > MAX_FILE_SIZE_MB:
        return f"File qua lon ({size_mb:.1f} MB). Gioi han {MAX_FILE_SIZE_MB} MB."
    return None


def _check_ollama() -> bool:
    try:
        import ollama as _ollama
        _ollama.list()
        return True
    except Exception:
        return False


# ── Sidebar: config ──────────────────────────────────────────────────

# Use defaults from config — no UI config needed
llm_model = OLLAMA_MODEL
embed_model = EMBEDDING_MODEL
collection_name = CHROMA_COLLECTION
top_k = 3
threshold = 0.50

output_dir = Path("outputs")


# ══════════════════════════════════════════════════════════════════════
# SECTION 1: Upload & Run
# ══════════════════════════════════════════════════════════════════════

st.markdown("---")
st.subheader("📤 Upload & So sanh")

col1, col2 = st.columns(2)
with col1:
    file_v1 = st.file_uploader("📄 Phien ban cu (v1)", type=["docx", "pdf"], key="file_v1")
    err_v1 = _validate_file(file_v1)
    if err_v1:
        st.error(err_v1)

with col2:
    file_v2 = st.file_uploader("📄 Phien ban moi (v2)", type=["docx", "pdf"], key="file_v2")
    err_v2 = _validate_file(file_v2)
    if err_v2:
        st.error(err_v2)

can_run = file_v1 is not None and file_v2 is not None and not err_v1 and not err_v2

if st.button("🚀 Chay So Sanh", disabled=not can_run, type="primary", use_container_width=True):
    if not _check_ollama():
        st.error(
            "⚠️ Khong ket noi duoc toi Ollama. "
            "Hay dam bao Ollama dang chay (`ollama serve`) va model da duoc pull."
        )
        st.stop()

    tmp_dir = tempfile.mkdtemp(prefix="legal_cmp_")
    tmp_v1 = Path(tmp_dir) / file_v1.name
    tmp_v2 = Path(tmp_dir) / file_v2.name
    tmp_v1.write_bytes(file_v1.getvalue())
    tmp_v2.write_bytes(file_v2.getvalue())

    chroma_dir = Path("chroma_db")

    progress_bar = st.progress(0, text="Dang khoi tao...")
    status_text = st.empty()

    def on_progress(step: str, frac: float):
        progress_bar.progress(frac, text=step)
        status_text.caption(f"⏳ {step}")

    try:
        from src.pipeline import run_comparison_pipeline

        result = run_comparison_pipeline(
            file_v1=tmp_v1,
            file_v2=tmp_v2,
            chroma_dir=chroma_dir,
            output_dir=output_dir,
            llm_model=llm_model,
            embed_model=embed_model,
            collection_name=collection_name,
            top_k=top_k,
            threshold=threshold,
            on_progress=on_progress,
        )

        st.session_state['pipeline_result'] = result
        st.session_state['result_source'] = 'pipeline'

        progress_bar.progress(1.0, text="Hoan tat!")
        status_text.empty()
        st.success(
            f"✅ So sanh hoan tat! "
            f"{len(result['summary_df'])} dieu duoc phan tich. "
            f"Bao cao luu tai `{result['report_path']}`."
        )
    except Exception as exc:
        progress_bar.empty()
        status_text.empty()
        st.error(f"❌ Loi khi chay pipeline: {exc}")

elif not can_run and not st.session_state.get('pipeline_result'):
    st.info("📎 Upload 2 file (v1 va v2) roi nhan **Chay So Sanh**.")


# ══════════════════════════════════════════════════════════════════════
# SECTION 2: Report (shown when result is available)
# ══════════════════════════════════════════════════════════════════════

if st.session_state.get('pipeline_result'):
    raw = st.session_state['pipeline_result']
    source = st.session_state.get('result_source', 'pipeline')

    if source == 'file':
        report = raw
    else:
        report = raw['report']

    comparison_results = report.get('article_level_results', [])

    st.markdown("---")
    st.subheader("📊 Ket qua So sanh")

    render_metrics(report)
    st.markdown("---")

    tab_changes, tab_summary, tab_citations = st.tabs([
        "📝 Danh sach thay doi",
        "📋 Tom tat diem quan trong",
        "📌 Trich doan + Vi tri",
    ])

    with tab_changes:
        render_change_list(comparison_results)

    with tab_summary:
        render_key_summary(comparison_results)

    with tab_citations:
        render_citations(comparison_results)
