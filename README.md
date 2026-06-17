# RAG-based Legal Document Comparison

Công cụ so sánh hai phiên bản hợp đồng / văn bản pháp lý tiếng Việt, chạy hoàn
toàn **local**. Hệ thống đọc 2 file (V1 cũ, V2 mới), tách theo cấu trúc
Điều/Khoản, truy xuất ngữ nghĩa bằng vector store, ghép các khoản tương ứng giữa
hai phiên bản rồi dùng LLM giải thích thay đổi kèm bằng chứng (evidence).

Kiến trúc gồm 3 phần: **pipeline xử lý (`src/`)**, **API server FastAPI
(`api/`)** và **giao diện web React + Vite (`frontend/`)**.

---

## 1. Tính năng chính

- Nhận đầu vào **DOCX** hoặc **PDF** tiếng Việt.
- Chuẩn hóa văn bản và trích cấu trúc heading/numbering trực tiếp từ XML của Word.
- Tách văn bản theo cấu trúc pháp lý: **Điều → Khoản → Điểm/Tiểu mục**.
- Index ngữ nghĩa vào **ChromaDB** (cosine space, embedding tiếng Việt).
- Ghép cặp Khoản giữa V1/V2 bằng **article-level anchoring + hybrid retrieval**
  (Cosine + BM25), tránh ghép nhầm chéo Điều.
- Phân loại trạng thái mỗi khoản: `unchanged`, `changed`, `added`, `removed`.
- Dùng **LLM local (Ollama / Qwen2.5)** để viết kết luận có dẫn chứng cho các
  khoản thay đổi; tuân nguyên tắc _"không bằng chứng → không kết luận"_.
- Xuất báo cáo JSON đầy đủ + bản tóm tắt gọn, và xem **song song 2 văn bản** trên UI.

---

## 2. Kiến trúc tổng thể

```text
        ┌──────────────┐      HTTP/JSON       ┌────────────────────┐
        │  Frontend    │  ───────────────▶    │   FastAPI (api/)   │
        │  React+Vite  │  ◀───────────────     │                    │
        └──────────────┘                       └─────────┬──────────┘
                                                         │ gọi
                                                         ▼
                                              ┌────────────────────┐
                                              │  Pipeline (src/)   │
                                              │  ingest → chunk →  │
                                              │  index → compare → │
                                              │  report            │
                                              └─────────┬──────────┘
                                                        │
                                   ┌────────────────────┼────────────────────┐
                                   ▼                    ▼                    ▼
                            ChromaDB (vector)   SentenceTransformer    Ollama (LLM)
```

### Luồng dữ liệu một lần so sánh

1. **Upload** → người dùng chọn 2 file (V1, V2) trên frontend.
2. **POST `/api/compare`** → backend lưu file tạm, gọi `run_comparison_pipeline`.
3. **Ingest** ([src/ingest.py](src/ingest.py)) → đọc DOCX/PDF, normalize, trích numbering.
4. **Chunk** ([src/chunker.py](src/chunker.py)) → tách theo Điều, rồi explode xuống mức Khoản.
5. **Index** ([src/indexer.py](src/indexer.py)) → embed + upsert vào ChromaDB (reset mỗi lần chạy).
6. **Compare** ([src/comparator.py](src/comparator.py)) → anchor Điều, ghép Khoản, gọi LLM.
7. **Report** ([src/reporter.py](src/reporter.py)) → tạo JSON report + bản copilot gọn.
8. **Hiển thị** → frontend render metrics, danh sách thay đổi, và xem song song bằng `docx-preview`.

---

## 3. Thành phần chi tiết

### 3.1. Pipeline xử lý — `src/`

| File                                   | Vai trò                                                                                                                                               |
| -------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| [src/ingest.py](src/ingest.py)         | Đọc DOCX (kèm style/heading/numbering từ XML Word) và PDF; chuẩn hóa whitespace/newline.                                                              |
| [src/chunker.py](src/chunker.py)       | Nhận diện Điều/Khoản/Điểm bằng regex + heading; `chunk_document` tạo chunk cấp Điều, `explode_to_khoan_chunks` tách xuống cấp Khoản.                  |
| [src/indexer.py](src/indexer.py)       | Load embedding model, tokenize tiếng Việt (pyvi), embed (L2-normalized) và upsert vào ChromaDB; `reset_collection` xóa vector cũ trước mỗi run.       |
| [src/retriever.py](src/retriever.py)   | Gom chunk thành "article", query vector candidates, chuyển cosine distance → similarity; sort key cho số Điều/Khoản dạng ghép (vd `1.10`).            |
| [src/comparator.py](src/comparator.py) | Lõi nghiệp vụ: anchor Điều V1↔V2, ghép Khoản theo P2 (khớp số) / P3 (hybrid Cosine+BM25), gán `added`/`removed` deterministic, gọi LLM cho `changed`. |
| [src/reporter.py](src/reporter.py)     | Tổng hợp kết quả thành report JSON, summary/citation DataFrame, bản copilot JSON/TXT.                                                                 |
| [src/pipeline.py](src/pipeline.py)     | `run_comparison_pipeline` — điều phối toàn bộ các bước trên end-to-end.                                                                               |

**Cơ chế ghép cặp (comparator):**

- **Article-level anchoring** — mỗi Điều V1 được neo vào tối đa một Điều V2 dựa
  trên độ tương đồng tiêu đề + nội dung (`ANCHOR_TITLE_WEIGHT=0.40`,
  `ANCHOR_BODY_WEIGHT=0.60`, ngưỡng `ANCHOR_MIN_SCORE=0.30`). Việc ghép Khoản chỉ
  diễn ra trong cặp Điều đã neo, tránh "cross-article contamination".
- **P2 — exact number match**: cùng số Khoản và độ tương đồng body ≥
  `P2_MIN_TEXT_SIMILARITY (0.40)`.
- **P3 — hybrid retrieval**: `score = 0.70·cosine + 0.30·bm25`, chỉ nhận khi ≥
  `COSINE_LOW (0.50)` và ứng viên nằm trong Điều đã anchor.
- Không có match → `removed` (V1) hoặc `added` (V2), không cần LLM.

### 3.2. API server — `api/` (FastAPI)

| File                                               | Vai trò                                                                                                       |
| -------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| [api/main.py](api/main.py)                         | Khởi tạo FastAPI, CORS, load embedding model một lần khi startup (lifespan), mount router dưới prefix `/api`. |
| [api/routes/compare.py](api/routes/compare.py)     | `POST /api/compare` — nhận 2 file, chạy pipeline trong thread pool, trả `CompareResponse` + lưu session DOCX. |
| [api/routes/documents.py](api/routes/documents.py) | `GET /api/docx/{session_id}/{version}` (và `/pdf/...` legacy) — phục vụ file gốc cho chế độ xem song song.    |
| [api/routes/health.py](api/routes/health.py)       | `GET /api/health` — báo trạng thái embedding model và Ollama.                                                 |
| [api/schemas.py](api/schemas.py)                   | Pydantic models: `ComparisonItem`, `EvidenceItem`, `ReportConfig`, `CompareResponse`, `HealthResponse`.       |
| [api/session_store.py](api/session_store.py)       | Lưu tạm đường dẫn DOCX V1/V2 theo `session_id` (in-memory, thread-safe).                                      |
| [api/state.py](api/state.py)                       | Giữ instance embedding model dùng chung toàn app.                                                             |

**Các endpoint:**

| Method | Path                               | Mô tả                                            |
| ------ | ---------------------------------- | ------------------------------------------------ |
| `POST` | `/api/compare`                     | Chạy so sánh 2 file, trả kết quả + `session_id`. |
| `GET`  | `/api/docx/{session_id}/{version}` | Tải file DOCX gốc (`version` = `v1`/`v2`).       |
| `GET`  | `/api/health`                      | Kiểm tra embedding model + Ollama.               |

### 3.3. Giao diện — `frontend/` (React + Vite + Tailwind)

| File                                                          | Vai trò                                      |
| ------------------------------------------------------------- | -------------------------------------------- |
| [frontend/src/App.tsx](frontend/src/App.tsx)                  | Khung ứng dụng, điều hướng giữa các tab.     |
| `frontend/src/components/UploadPanel.tsx`                     | Chọn & validate file V1/V2.                  |
| `frontend/src/components/CompareTab.tsx`                      | Trigger so sánh và hiển thị kết quả.         |
| `frontend/src/components/MetricsSummary.tsx`                  | Thẻ thống kê trạng thái.                     |
| `frontend/src/components/ChangeCard.tsx`                      | Một mục thay đổi (kết luận + evidence).      |
| `frontend/src/components/SideBySideTab.tsx` + `DocViewer.tsx` | Xem song song 2 văn bản bằng `docx-preview`. |
| `frontend/src/components/StatusBanner.tsx`                    | Báo trạng thái embedding/Ollama.             |

Vite proxy chuyển mọi request `/api` sang `http://127.0.0.1:8000` (xem
[frontend/vite.config.ts](frontend/vite.config.ts)).

### 3.4. Cấu hình & tiện ích

| File                                           | Vai trò                                                                                                                             |
| ---------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| [configs/defaults.py](configs/defaults.py)     | Hằng số mặc định: model, collection, thresholds.                                                                                    |
| [scripts/eval_pairs.py](scripts/eval_pairs.py) | Benchmark toàn bộ cặp trong `data/document` so với CHANGELOG `.md`, rollup khoản→Điều, xuất `outputs/eval_pairs/eval_summary.json`. |

**Tham số cốt lõi** (trong [configs/defaults.py](configs/defaults.py)):

| Tham số           | Giá trị                            | Ý nghĩa                               |
| ----------------- | ---------------------------------- | ------------------------------------- |
| `EMBEDDING_MODEL` | `huyydangg/DEk21_hcmute_embedding` | Embedding tiếng Việt (768 chiều).     |
| `OLLAMA_MODEL`    | `qwen2.5:7b-instruct-q4_K_M`       | LLM local sinh kết luận.              |
| `COSINE_HIGH`     | `0.85`                             | ≥ ngưỡng → match chắc chắn (matched). |
| `COSINE_LOW`      | `0.50`                             | < ngưỡng → no_match → removed/added.  |

---

## 4. Cấu trúc thư mục

```text
rag-based-legal-comparison/
├─ api/                  # FastAPI backend
│  ├─ main.py            # entry point, lifespan, CORS, routers
│  ├─ routes/            # compare / documents / health
│  ├─ schemas.py         # Pydantic request/response models
│  ├─ session_store.py   # lưu tạm DOCX theo session
│  └─ state.py           # embedding model dùng chung
├─ frontend/             # React + Vite + Tailwind UI
│  ├─ src/
│  │  ├─ App.tsx
│  │  ├─ components/     # Upload, Compare, SideBySide, DocViewer...
│  │  ├─ api/            # client gọi backend
│  │  └─ types.ts
│  ├─ vite.config.ts     # proxy /api → :8000
│  └─ package.json
├─ src/                  # Pipeline xử lý
│  ├─ ingest.py          # đọc DOCX/PDF + normalize
│  ├─ chunker.py         # chia Điều/Khoản/Điểm
│  ├─ indexer.py         # embed + ChromaDB
│  ├─ retriever.py       # truy vấn ngữ nghĩa
│  ├─ comparator.py      # anchor + ghép Khoản + LLM
│  ├─ reporter.py        # sinh báo cáo
│  └─ pipeline.py        # điều phối end-to-end
├─ configs/
│  └─ defaults.py        # model + thresholds
├─ scripts/
│  └─ eval_pairs.py      # benchmark vs CHANGELOG
├─ data/                 # cặp tài liệu mẫu (pair 1..10)
├─ outputs/              # report JSON, chunks (tự sinh)
├─ chroma_db/            # ChromaDB persistent (tự sinh)
├─ notebooks/            # notebook tham khảo
├─ requirements.txt
└─ README.md
```

---

## 5. Yêu cầu hệ thống

| Thành phần  | Yêu cầu                                                            |
| ----------- | ------------------------------------------------------------------ |
| Python      | 3.10+ (đã test 3.13)                                               |
| Node.js     | 18+ (cho frontend)                                                 |
| RAM         | 8GB+                                                               |
| GPU         | NVIDIA CUDA 12.x (khuyến nghị, để chạy embedding nhanh)            |
| HuggingFace | Cần `HF_TOKEN` để tải embedding model                              |
| Ollama      | Cần chạy `ollama serve` và pull model `qwen2.5:7b-instruct-q4_K_M` |

---

## 6. Cài đặt

### 6.1. Backend (Python)

```powershell
# Tạo & kích hoạt môi trường ảo
python -m venv .venv
.venv\Scripts\Activate.ps1        # Windows
# source .venv/bin/activate       # Linux/macOS

# Cài dependencies
pip install -r requirements.txt
```

Tạo file `.env` (tham khảo `.env.example`) và đặt token HuggingFace:

```env
HF_TOKEN=hf_xxxxxxxxxxxxxxxx
```

### 6.2. Ollama (LLM local)

```powershell
ollama serve
ollama pull qwen2.5:7b-instruct-q4_K_M
```

### 6.3. Frontend (Node)

```powershell
cd frontend
npm install
```

---

## 7. Chạy ứng dụng

Mở **2 terminal**:

**Terminal 1 — API server:**

```powershell
.venv\Scripts\Activate.ps1
uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload
```

**Terminal 2 — Frontend:**

```powershell
cd frontend
npm run dev
```

Truy cập UI tại **http://localhost:5173** (Vite tự proxy `/api` sang cổng 8000).

API docs (Swagger) tại **http://localhost:8000/docs**.

---

## 8. Đánh giá độ chính xác (benchmark)

Chạy toàn bộ cặp tài liệu trong `data/document/` và so với bản chuẩn CHANGELOG:

```powershell
.venv\Scripts\Activate.ps1
python scripts/eval_pairs.py
```

Script gom kết quả khoản-level lên cấp Điều và đối chiếu số Điều
`removed / added / changed` với bảng tổng kết trong file `.md`. Kết quả chi tiết
lưu tại `outputs/eval_pairs/eval_summary.json`.

> Lưu ý: bản chuẩn đếm theo **Điều**, còn pipeline chạy theo **Khoản**, nên đây
> là phép so xấp xỉ ở cấp Điều (rollup), không phải khớp tuyệt đối.

---

## 9. Định dạng kết quả (`CompareResponse`)

```jsonc
{
  "session_id": "uuid",
  "config": {
    "file_v1": "HopDong_V1.docx",
    "file_v2": "HopDong_V2.docx",
    "total_khoans": 71,
    "status_counts": {
      "unchanged": 56,
      "changed": 11,
      "removed": 4,
      "added": 5,
    },
    "grounded_count": 71,
    "llm_used_count": 11,
  },
  "results": [
    {
      "article_number": "13.2",
      "dieu_number": "13",
      "khoan_number": "2",
      "article_title": "Thẩm Quyền Và Trách Nhiệm Của Tổng Giám Đốc",
      "status": "changed",
      "match_score": 0.97,
      "matched_article_v2": "12.2",
      "conclusion": "...",
      "grounded": true,
      "llm_used": true,
      "evidence": [{ "tag": "changed", "before": "...", "after": "..." }],
    },
  ],
  "has_docx_v1": true,
  "has_docx_v2": true,
}
```
