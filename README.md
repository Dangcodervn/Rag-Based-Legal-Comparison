# RAG-based Legal Document Comparison

Công cụ so sánh văn bản pháp luật Việt Nam sử dụng RAG (Retrieval-Augmented Generation) chạy hoàn toàn **local/offline**.

## Tính năng

- Đọc văn bản luật định dạng DOCX và PDF
- Tự động phân tách theo cấu trúc pháp lý: **Header → Chương → Mục → Điều**
- Nhúng vector bằng model tiếng Việt `huyydangg/DEk21_hcmute_embedding`
- Lưu trữ và tìm kiếm ngữ nghĩa bằng ChromaDB
- So sánh điều khoản giữa phiên bản v1 và v2 (đang phát triển)
- Sinh báo cáo tự động bằng Qwen2.5 qua Ollama (đang phát triển)

## Yêu cầu hệ thống

| Thành phần          | Yêu cầu tối thiểu                            |
| ------------------- | -------------------------------------------- |
| Python              | 3.10+                                        |
| GPU                 | NVIDIA với CUDA 12.x (khuyến nghị ≥6GB VRAM) |
| RAM                 | 8GB+                                         |
| Ollama              | 0.17+ (để chạy LLM local)                    |
| HuggingFace account | Cần token để tải embedding model             |

## Cài đặt

### 1. Clone repository

```bash
git clone https://github.com/<your-username>/rag-based-legal-comparison.git
cd rag-based-legal-comparison
```

### 2. Tạo môi trường ảo và cài dependencies

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt
```

> **Lưu ý về PyTorch + CUDA:** `requirements.txt` chỉ định `torch==2.6.0+cu124`.
> Nếu máy bạn dùng CUDA khác hoặc không có GPU, hãy cài PyTorch phù hợp từ [pytorch.org](https://pytorch.org/get-started/locally/) trước khi chạy `pip install -r requirements.txt`.

### 3. Cấu hình HuggingFace token

```bash
cp .env.example .env
```

Mở file `.env` và điền token:

```
HF_TOKEN=hf_xxxxxxxxxxxxxxxxxxxx
```

Lấy token tại: <https://huggingface.co/settings/tokens>

### 4. Cài đặt Ollama và tải model LLM

```bash
# Tải Ollama tại https://ollama.com/download rồi cài đặt
# Sau đó tải model Qwen2.5:
ollama pull qwen2.5:7b-instruct-q4_K_M
```

### 5. Đặt file văn bản luật vào đúng thư mục

```
data/sample_pairs/standalone/   ← file DOCX/PDF đơn lẻ (chỉ 1 phiên bản)
data/sample_pairs/pairs/        ← cặp v1 + v2 để so sánh (Pha B)
```

## Sử dụng

### Pha A: Kiểm thử pipeline ingest

Mở notebook và chạy tuần tự theo thứ tự cell:

```
notebooks/Ingestion_pipeline_test.ipynb
```

| Cell | Mục đích                        | GPU cần? |
| ---- | ------------------------------- | -------- |
| 2    | Import + paths                  | Không    |
| 3    | Hàm đọc DOCX/PDF                | Không    |
| 4    | normalize_text                  | Không    |
| 5    | chunk_full_hierarchy            | Không    |
| 6    | Ingest test 8 files (assert)    | Không    |
| 7    | Export JSONL ra outputs/        | Không    |
| 8    | Đăng nhập HuggingFace           | Không    |
| 9    | Load embedding model + ChromaDB | **Có**   |
| 10   | Full pipeline → ChromaDB        | **Có**   |
| 11   | Thống kê Chroma                 | Không    |
| 12   | Xem mẫu từng loại chunk         | Không    |

## Cấu trúc thư mục

```
rag-based-legal-comparison/
├── data/
│   ├── raw/                        # File gốc chưa xử lý
│   ├── processed/                  # File đã tiền xử lý
│   └── sample_pairs/
│       ├── standalone/             # DOCX/PDF đơn lẻ
│       └── pairs/                  # Cặp v1 + v2 để so sánh
├── notebooks/
│   └── Ingestion_pipeline_test.ipynb
├── outputs/                        # JSONL chunks (tự sinh, không commit)
├── chroma_db/                      # ChromaDB persistent (tự sinh, không commit)
├── src/
│   ├── ingest/                     # Đọc file
│   ├── chunking/                   # Phân tách điều khoản
│   ├── embedding/                  # Nhúng vector
│   ├── comparison/                 # So sánh v1 vs v2
│   ├── report/                     # Sinh báo cáo
│   └── ui/                         # Streamlit UI
├── configs/
├── tests/
├── .env.example                    # Template cấu hình
├── requirements.txt
└── README.md
```

## Lộ trình phát triển

- [x] **Pha A**: Ingest pipeline — DOCX/PDF → Normalize → Chunk → Embed → ChromaDB
- [ ] **Pha B**: So sánh điều khoản — matching Điều X (v1) ↔ Điều X (v2) + diff engine
- [ ] **Pha C**: Sinh báo cáo — LLM tóm tắt thay đổi với trích dẫn nguồn
- [ ] **Pha D**: Giao diện Streamlit

## Ghi chú kỹ thuật

- Embedding model: `huyydangg/DEk21_hcmute_embedding` (768 chiều), cần word segmentation bằng `pyvi.ViTokenizer`
- Chunk type: `header` | `article` | `definition`
- Vector DB: ChromaDB 1.5.2 persistent, collection `legal_chunks`
- LLM local: Qwen2.5:7b-instruct-q4_K_M qua Ollama
- File `.env` và `chroma_db/` **không được commit** (xem `.gitignore`)
