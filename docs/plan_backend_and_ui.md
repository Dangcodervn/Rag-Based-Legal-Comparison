# Ke hoach: Dong goi Backend + Tao Web UI

## Hien trang

```
src/              # Trong (chi co __init__.py)
configs/          # defaults.py co san LLM/embed config
notebooks/        # Toan bo logic nam trong Comparison_report_demo.ipynb
requirements.txt  # Da co streamlit, ollama, chromadb, sentence-transformers...
```

Toan bo code dang nam trong 6 cell notebook. Can tach thanh module Python
de tai su dung cho API/UI.

---

## PHAN 1: Dong goi Backend Modules

### Cau truc thu muc muc tieu

```
src/
├── __init__.py
├── ingest.py          # Doc DOCX/PDF, normalize text
├── chunker.py         # Chunk theo Dieu/Khoan/Diem
├── indexer.py         # Embedding + ChromaDB index
├── retriever.py       # Vector query, candidate matching
├── comparator.py      # LLM compare + evidence + grounding
├── reporter.py        # Tao bao cao JSON/DataFrame/Markdown
└── pipeline.py        # Orchestrator: goi tat ca buoc tu file -> bao cao
```

### Chi tiet tung module

#### 1. `src/ingest.py` (tu Cell 3 — phan Doc)

- Copy cac ham: `read_docx_document`, `read_pdf_text`, `read_document`
- Copy cac ham XML helper: `_w_attr`, `_read_docx_xml`, `_parse_docx_style_map`,
  `_parse_docx_numbering`, `_resolve_style_numbering`, `_render_numbering_label`,
  `_extract_paragraph_numbering`, `_get_heading_level`
- Copy cac ham format: `_to_roman`, `_to_alpha`, `_format_counter`
- Copy `normalize_text`, `normalize_document`, `normalize_ws`
- **Interface chinh:**
  ```python
  def read_and_normalize(path: Path) -> dict:
      """Doc file DOCX/PDF, tra ve document dict da normalize."""
  ```

#### 2. `src/chunker.py` (tu Cell 3 — phan Chunking)

- Copy regex: `CHUONG_RE`, `MUC_RE`, `DIEU_RE`, `KHOAN_RE`, `DIEM_RE`, `DINH_NGHIA_RE`
- Copy cac ham: `_clean_heading`, `_looks_upper_heading`, `_looks_title_heading`,
  `_is_contract_section_heading`, `_extract_khoan_items`, `_build_chunk`,
  `_chunk_docx_headings`, `_chunk_plain_text`, `chunk_full_hierarchy`
- **Interface chinh:**
  ```python
  def chunk_document(document: dict, doc_id: str, version: str) -> list[dict]:
      """Chia document thanh danh sach chunk theo Dieu."""
  ```

#### 3. `src/indexer.py` (tu Cell 4)

- Copy: `load_embedder`, `get_collection`, `embed_chunks`, `index_chunks`
- **Interface chinh:**
  ```python
  def build_index(chunks: list[dict], chroma_dir: Path,
                  embedder, collection_name: str) -> int:
      """Embed va index chunks vao ChromaDB. Tra ve so chunk da index."""
  ```

#### 4. `src/retriever.py` (tu Cell 5 — phan vector query)

- Copy: `_distance_to_similarity`, `query_candidates_for_article`,
  `build_articles_from_chunks`, `article_sort_key`
- **Interface chinh:**
  ```python
  def find_matching_article(article_text: str, target_version: str,
                            chroma_dir: Path, embedder,
                            top_k: int, threshold: float) -> dict | None:
      """Tim dieu tuong ung trong phien ban kia bang vector search."""
  ```

#### 5. `src/comparator.py` (tu Cell 5 — phan LLM + grounding)

- Copy: `shorten`, `diff_excerpt`, `extract_evidence`, `parse_first_json_object`,
  `_status_from_texts`, `_normalize_evidence_items`,
  `enforce_no_evidence_no_conclusion`, `llm_compare_article`
- Copy: `compare_articles_with_vector_retrieval`
- **Interface chinh:**
  ```python
  def compare_two_versions(chunks_v1, chunks_v2, chroma_dir, embedder,
                           llm_model, top_k, threshold) -> list[dict]:
      """So sanh 2 phien ban, tra ve danh sach ket qua theo dieu."""
  ```

#### 6. `src/reporter.py` (tu Cell 6)

- Tao summary DataFrame, citation DataFrame, JSON report payload
- **Interface chinh:**

  ```python
  def build_report(comparison_results: list[dict],
                   config: dict) -> dict:
      """Tra ve report payload (dict) gom config + article_level_results."""

  def build_summary_df(comparison_results: list[dict]) -> pd.DataFrame:
      """Tra ve bang tom tat."""

  def build_citation_df(comparison_results: list[dict]) -> pd.DataFrame:
      """Tra ve bang trich dan."""

  def save_report_json(report: dict, output_path: Path) -> Path:
      """Luu report ra file JSON."""
  ```

#### 7. `src/pipeline.py` (Orchestrator moi)

- Goi lien tiep: ingest → chunk → index → compare → report
- **Interface chinh:**
  ```python
  def run_comparison_pipeline(
      file_v1: Path,
      file_v2: Path,
      chroma_dir: Path,
      output_dir: Path,
      llm_model: str,
      embed_model: str,
      top_k: int = 3,
      threshold: float = 0.5,
      on_progress: Callable | None = None,   # callback cho UI
  ) -> dict:
      """
      Full pipeline: 2 file -> bao cao JSON + DataFrames.
      Tra ve:
        {
          'report': dict,          # payload day du
          'summary_df': DataFrame,
          'citation_df': DataFrame,
          'report_path': Path,
        }
      """
  ```

### Buoc thuc hien (Phan 1)

| Buoc | Viec                                                 | Uoc luong |
| ---- | ---------------------------------------------------- | --------- |
| 1.1  | Tao `src/ingest.py` — copy + chinh interface         | nhanh     |
| 1.2  | Tao `src/chunker.py` — copy + chinh interface        | nhanh     |
| 1.3  | Tao `src/indexer.py` — copy + chinh interface        | nhanh     |
| 1.4  | Tao `src/retriever.py` — copy + chinh interface      | nhanh     |
| 1.5  | Tao `src/comparator.py` — copy + chinh interface     | nhanh     |
| 1.6  | Tao `src/reporter.py` — tao moi tu Cell 6            | nhanh     |
| 1.7  | Tao `src/pipeline.py` — orchestrator                 | vua       |
| 1.8  | Test: chay `pipeline.run_comparison_pipeline()` voi  | vua       |
|      | sample v1/v2, kiem tra output giong notebook         |           |
| 1.9  | Cap nhat notebook: import tu src thay vi inline code | nhanh     |

---

## PHAN 2: API + Web UI

### Stack chon

- **UI:** Streamlit (da co trong requirements.txt)
- **Ly do:** Khong can tach backend API rieng vi Streamlit goi truc tiep
  Python function. Don gian, phu hop prototype/demo. Neu can API rieng
  sau nay thi them FastAPI layer boc `pipeline.py`.

### Cau truc file

```
app/
├── streamlit_app.py     # Entry point: streamlit run app/streamlit_app.py
├── pages/
│   ├── 1_Upload.py      # Trang upload 2 file
│   ├── 2_Report.py      # Trang xem bao cao
│   └── 3_History.py     # (Optional) Xem lai bao cao cu
└── components/
    └── report_view.py   # Render bang, chart, citation
```

### Man hinh & luong su dung

```
[Trang Upload]
  ├── Upload file v1 (DOCX/PDF)
  ├── Upload file v2 (DOCX/PDF)
  ├── Cau hinh (LLM model, top_k, threshold) — co gia tri mac dinh
  ├── Nut [Chay So Sanh]
  │     └── Progress bar (callback tu pipeline)
  └── Khi xong → chuyen sang Trang Report

[Trang Report]
  ├── Tong quan: so dieu, unchanged/changed/added/removed, grounded %
  ├── Bang tom tat (summary_df) — loc theo trang thai
  ├── Bang trich dan (citation_df) — hien thi evidence
  ├── Xem chi tiet tung dieu (expand)
  │     ├── Text v1 vs v2 (side-by-side hoac diff highlight)
  │     ├── Ket luan LLM
  │     └── Evidence items
  ├── Download JSON report
  └── Download Markdown report (optional)
```

### Xu ly loi & gioi han

| Tinh huong                   | Xu ly                                            |
| ---------------------------- | ------------------------------------------------ |
| File khong phai DOCX/PDF     | Hien thong bao loi, khong cho chay               |
| File qua lon (>10MB)         | Canh bao, cho phep tiep tuc                      |
| Ollama khong chay            | Fallback rule-based, hien canh bao               |
| LLM timeout                  | Retry 1 lan, neu fail dung fallback              |
| Khong tim thay dieu nao      | Hien "Khong phat hien cau truc dieu khoan"       |
| Ket luan khong co bang chung | Hien ro "Can kiem tra thu cong" (grounded=False) |

### Buoc thuc hien (Phan 2)

| Buoc | Viec                                                 | Uoc luong |
| ---- | ---------------------------------------------------- | --------- |
| 2.1  | Tao `app/streamlit_app.py` — layout chinh + sidebar  | nhanh     |
| 2.2  | Tao trang Upload — form upload + config + nut chay   | vua       |
| 2.3  | Ket noi voi `pipeline.run_comparison_pipeline()`     | vua       |
| 2.4  | Tao trang Report — render bang + citation + chi tiet | vua       |
| 2.5  | Them download JSON/Markdown                          | nhanh     |
| 2.6  | Xu ly loi: file sai dinh dang, LLM khong co          | nhanh     |
| 2.7  | Test end-to-end voi sample v1/v2                     | vua       |

---

## Thu tu trien khai khuyen nghi

```
Phan 1 (Backend modules)
  1.1 → 1.2 → 1.3 → 1.4 → 1.5 → 1.6 → 1.7 → 1.8 → 1.9

Phan 2 (UI)
  2.1 → 2.2 → 2.3 → 2.4 → 2.5 → 2.6 → 2.7
```

Phan 1 lam truoc hoan toan, test xong roi moi bat dau Phan 2.
Phan 2 chi goi function tu `src/`, khong viet logic moi.

---

## Luu y ky thuat

1. **Khong duplicate code:** Notebook sau khi refactor se `from src.pipeline import ...`
   thay vi giu code inline.
2. **Config tap trung:** Dung `configs/defaults.py` cho gia tri mac dinh,
   cho phep override qua tham so ham hoac .env.
3. **Logging:** Dung `loguru` (da co trong requirements) thay vi print.
4. **Chroma isolation:** Moi lan chay tao collection name rieng (theo timestamp
   hoac pair ID) de tranh xung dot khi so sanh nhieu cap.
5. **File tam:** Upload file luu vao `data/uploads/` hoac temp dir,
   don dep sau khi xong.
6. **Security:** Validate file extension + size truoc khi xu ly.
   Khong cho upload file thuc thi.
