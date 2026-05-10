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
    COSINE_LOW,
)
from app.components.report_view import (
    render_metrics,
    render_change_list,
    render_key_summary,
    render_document_view,
)

st.set_page_config(
    page_title="So Sánh Văn Bản Pháp Lý",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Custom CSS ───────────────────────────────────────────────────────
st.markdown("""
<style>
/* Header */
.app-header { padding: 1.5rem 0 0.5rem 0; border-bottom: 2px solid #e2e8f0; margin-bottom: 1.5rem; }
.app-title  { font-size: 1.8rem; font-weight: 700; color: #1e293b; margin: 0; }
.app-sub    { font-size: 0.9rem; color: #64748b; margin-top: 0.2rem; }

/* Upload cards */
.upload-card {
    border: 1.5px dashed #cbd5e1;
    border-radius: 12px;
    padding: 1rem 1.2rem;
    background: #f8fafc;
    transition: border-color 0.2s;
}
.upload-card:hover { border-color: #6366f1; }

/* Divider */
.section-divider { border: none; border-top: 1px solid #e2e8f0; margin: 1.5rem 0; }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="app-header">
  <div class="app-title">⚖️ Trợ lý So sánh Văn bản Pháp lý</div>
  <div class="app-sub">Phân tích thay đổi giữa 2 phiên bản hợp đồng / văn bản pháp lý</div>
</div>
""", unsafe_allow_html=True)

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
threshold = COSINE_LOW

output_dir = Path("outputs")


# ══════════════════════════════════════════════════════════════════════
# SECTION 1: Upload & Run
# ══════════════════════════════════════════════════════════════════════

st.markdown("### 📂 Chọn tài liệu cần so sánh")
st.markdown("Tải lên 2 phiên bản của cùng một văn bản (DOCX hoặc PDF, tối đa 10 MB mỗi file).")

col1, col2 = st.columns(2, gap="large")
with col1:
    st.markdown("**📄 Phiên bản cũ (V1)**")
    file_v1 = st.file_uploader("Chọn file V1", type=["docx", "pdf"], key="file_v1", label_visibility="collapsed")
    err_v1 = _validate_file(file_v1)
    if err_v1:
        st.error(err_v1)
    elif file_v1:
        st.success(f"✔ {file_v1.name}  ({file_v1.size / 1024:.0f} KB)")

with col2:
    st.markdown("**📄 Phiên bản mới (V2)**")
    file_v2 = st.file_uploader("Chọn file V2", type=["docx", "pdf"], key="file_v2", label_visibility="collapsed")
    err_v2 = _validate_file(file_v2)
    if err_v2:
        st.error(err_v2)
    elif file_v2:
        st.success(f"✔ {file_v2.name}  ({file_v2.size / 1024:.0f} KB)")

can_run = file_v1 is not None and file_v2 is not None and not err_v1 and not err_v2

st.markdown("<hr class='section-divider'>", unsafe_allow_html=True)

if not can_run and not st.session_state.get('pipeline_result'):
    st.info("⬆️ Tải lên cả 2 file phía trên để bắt đầu so sánh.")

if st.button("🚀 Bắt đầu So sánh", disabled=not can_run, type="primary", use_container_width=True):
    if not _check_ollama():
        st.error(
            "⚠️ Không kết nối được tới Ollama. "
            "Hãy đảm bảo Ollama đang chạy (`ollama serve`) và model đã được pull."
        )
        st.stop()

    tmp_dir = tempfile.mkdtemp(prefix="legal_cmp_")
    tmp_v1 = Path(tmp_dir) / file_v1.name
    tmp_v2 = Path(tmp_dir) / file_v2.name
    tmp_v1.write_bytes(file_v1.getvalue())
    tmp_v2.write_bytes(file_v2.getvalue())

    chroma_dir = Path("chroma_db")

    progress_bar = st.progress(0, text="Đang khởi tạo...")
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

        progress_bar.progress(1.0, text="Hoàn tất!")
        status_text.empty()
        n = len(result['summary_df'])
        st.success(f"✅ So sánh hoàn tất — {n} khoản đã phân tích. Báo cáo lưu tại `{result['report_path']}`.")
    except Exception as exc:
        progress_bar.empty()
        status_text.empty()
        st.error(f"❌ Lỗi khi chạy pipeline: {exc}")

elif not can_run and not st.session_state.get('pipeline_result'):
    pass  # hint shown above


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

    st.markdown("<hr class='section-divider'>", unsafe_allow_html=True)
    st.markdown("### 📊 Kết quả So sánh")

    render_metrics(report)
    st.markdown("<hr class='section-divider'>", unsafe_allow_html=True)

    tab_changes, tab_summary, tab_doc = st.tabs([
        "📝 Danh sách thay đổi",
        "📋 Tóm tắt điểm quan trọng",
        "📄 Xem Song Song",
    ])

    with tab_changes:
        render_change_list(comparison_results)

    with tab_summary:
        render_key_summary(comparison_results)

    with tab_doc:
        render_document_view(comparison_results)
