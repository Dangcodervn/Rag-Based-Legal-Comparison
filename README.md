# RAG-based Legal Document Comparison

Công cụ so sánh hai phiên bản hợp đồng hoặc văn bản pháp lý tiếng Việt bằng pipeline local: đọc file, chuẩn hóa, chia đoạn, truy xuất đoạn liên quan, sau đó phục vụ bước so sánh và sinh báo cáo.

## Mục tiêu hiện tại

- Nhận đầu vào DOCX hoặc PDF tiếng Việt.
- Chuẩn hóa văn bản để giảm nhiễu do xuống dòng, khoảng trắng, ký tự lạ.
- Chia văn bản thành 3 loại chunk có ý nghĩa cho so sánh:
  - `header`: phần mở đầu tài liệu.
  - `article`: điều khoản hoặc mục nội dung chính.
  - `definition`: phần định nghĩa hoặc giải thích thuật ngữ.
- Xuất chunk ra JSONL để dùng cho bước retrieval và comparison.

## Trạng thái hiện tại

- Đã hỗ trợ tốt cho hợp đồng có heading kiểu `Đối Tượng Của Hợp Đồng`, `Vốn Điều Lệ`, `Thời Hạn...`.
- Vẫn giữ tương thích với văn bản có dạng `Điều 1`, `Điều 2`.
- Đã hoàn thiện phần so sánh v1/v2 và sinh báo cáo thay đổi.
- Đã có module index vào ChromaDB và truy vấn ngữ nghĩa.
- Chưa hoàn thiện UI Streamlit.

## Thành phần chính

### `src/reader.py`

- Đọc DOCX và PDF.
- Trả về text thô từ file.

### `src/normalizer.py`

- Chuẩn hóa newline, khoảng trắng, non-breaking space.
- Giúp regex ổn định hơn trước khi chunking.

### `src/chunker.py`

- Parser hiện tại chỉ phân loại semantic thành `header`, `article`, `definition`.
- Hỗ trợ hai kiểu heading:
  - Dạng luật: `Điều 1`, `Điều 2`, `Chương I`, `Mục 1`.
  - Dạng hợp đồng: heading độc lập như `Định Nghĩa`, `Đối Tượng Của Hợp Đồng`, `Tài Sản...`.

### `scripts/process_pairs.py`

- Xử lý một cặp tài liệu v1/v2.
- Xuất:
  - `outputs/pair_processing_results.json`
  - `outputs/sample_v1_chunks.jsonl`
  - `outputs/sample_v2_chunks.jsonl`

### `src/indexer.py`

- Embed chunks bằng model `huyydangg/DEk21_hcmute_embedding` và upsert vào ChromaDB.
- Hỗ trợ đọc trực tiếp từ file JSONL.

### `src/retriever.py`

- Truy vấn ngữ nghĩa: tokenize câu hỏi tiếng Việt, embed, query ChromaDB.
- Truy vấn theo metadata filter (không cần embedding).

### `src/comparator.py`

- So sánh hai file JSONL chunk (v1 vs v2) theo `clause_id`.
- Trả về danh sách `added`, `removed`, `modified`, `unchanged`.

### `src/reporter.py`

- Nhận kết quả diff từ comparator, sinh báo cáo JSON có citations.
- Lưu file báo cáo ra `outputs/comparison_report.json`.

### `scripts/process_pairs.py`

- Xử lý một cặp tài liệu v1/v2.
- Xuất chunks ra `outputs/` dạng JSONL.

### `scripts/build_index.py`

- Embed tất cả JSONL chunk files trong `outputs/` vào ChromaDB.
- Cần GPU hoặc CPU đủ mạnh và HF_TOKEN trong `.env`.

### `scripts/query_chunks.py`

- Tìm kiếm ngữ nghĩa từ dòng lệnh.
- Ví dụ: `python scripts/query_chunks.py "vốn điều lệ"`

### `scripts/compare_pair.py`

- So sánh v1 vs v2 và sinh báo cáo thay đổi.
- Không cần GPU, chạy trên JSONL đã có.

### `scripts/inspect_pairs.py`

- In tóm tắt số lượng chunk theo từng loại.

### `tests/test_ingestion_core.py`

- Test cho reader, normalizer và chunker.
- Bao gồm cả test với sample contract thật.

## Vì sao chỉ tập trung vào 3 loại chunk nhưng vẫn có nhiều trường?

Điểm cần phân biệt là:

- `chunk_type` chỉ có 3 giá trị: `header`, `article`, `definition`.
- Các trường còn lại không phải là loại chunk mới, mà là metadata đi kèm cho mỗi chunk.

Hiện tại output chunk có 3 nhóm thông tin:

### 1. Trường semantic cốt lõi

- `chunk_type`
- `article_title`
- `text`

Đây là phần trực tiếp phục vụ retrieval, so sánh và trích dẫn.

### 2. Trường nhận diện chunk

- `chunk_id`
- `doc_id`
- `version`
- `article_number`
- `clause_id`

Nhóm này dùng để ghép v1 với v2, theo dõi từng chunk và tạo báo cáo thay đổi.

### 3. Trường metadata tương thích

- `chuong_so`, `chuong_ten`
- `muc_so`, `muc_ten`
- `khoan_count`, `diem_count`
- `char_len`, `created_at`

Nhóm này tồn tại chủ yếu vì 2 lý do:

- Giữ tương thích với notebook cũ đang dùng các trường đó.
- Hỗ trợ về sau nếu cần hiển thị vị trí, thống kê hoặc filter nâng cao.

Với hợp đồng, nhiều trường trong nhóm này có thể là `0` hoặc rỗng. Điều đó không có nghĩa parser đang chia thành nhiều loại chunk; nó chỉ đang gắn thêm metadata cho cùng một chunk.

## Nếu muốn tối giản hơn nữa

Schema tối thiểu để chạy pipeline pair-comparison về sau chỉ cần:

```json
{
  "chunk_id": "sample_v1_0001",
  "doc_id": "sample_v1",
  "version": "sample",
  "chunk_type": "article",
  "article_number": "3",
  "article_title": "Đối Tượng Của Hợp Đồng",
  "clause_id": "clause_003",
  "text": "..."
}
```

Hiện tại tôi chưa cắt bớt ngay các trường phụ vì notebook và một phần code cũ vẫn đang dựa vào chúng.

## Cấu trúc thư mục hiện tại

```text
rag-based-legal-comparison/
  data/
    sample_pairs/
      standalone/
      pairs/
  notebooks/           # notebook tham khảo (không phải source of truth)
  outputs/             # JSONL chunks, báo cáo (tự sinh)
  chroma_db/           # ChromaDB persistent (tự sinh)
  scripts/
    process_pairs.py   # chia chunk cặp tài liệu
    build_index.py     # embed + upsert vào ChromaDB
    query_chunks.py    # tìm kiếm ngữ nghĩa
    compare_pair.py    # so sánh v1 vs v2 + báo cáo
    inspect_pairs.py   # kiểm tra nhanh kết quả chunking
  src/
    reader.py          # đọc DOCX/PDF
    normalizer.py      # chuẩn hóa text
    chunker.py         # chia chunk
    indexer.py         # embed + ChromaDB
    retriever.py       # truy vấn ngữ nghĩa
    comparator.py      # so sánh v1 vs v2
    reporter.py        # sinh báo cáo thay đổi
  tests/
    test_ingestion_core.py
  README.md
  requirements.txt
```

## Yêu cầu hệ thống

| Thành phần          | Yêu cầu tối thiểu                            |
| ------------------- | -------------------------------------------- |
| Python              | 3.10+                                        |
| RAM                 | 8GB+                                         |
| GPU                 | NVIDIA CUDA 12.x nếu chạy embedding trên GPU |
| HuggingFace account | Cần token để tải embedding model             |
| Ollama              | Cần nếu chạy phần LLM local                  |

## Cài đặt

### 1. Tạo môi trường ảo

```bash
python -m venv .venv
```

### 2. Kích hoạt môi trường

```bash
# Windows
.venv\Scripts\activate

# Linux / macOS
source .venv/bin/activate
```

### 3. Cài dependencies

```bash
pip install -r requirements.txt
```

### 4. Tạo file `.env`

```bash
copy .env.example .env
```

Điền token HuggingFace nếu cần tải embedding model:

```text
HF_TOKEN=hf_xxxxxxxxxxxxxxxxxxxx
```

### 5. Chuẩn bị dữ liệu

Đặt cặp tài liệu cần so sánh vào:

```text
data/sample_pairs/pairs/
```

Ví dụ:

```text
data/sample_pairs/pairs/
	sample v1.docx
	sample v2.docx
```

## Cách chạy pipeline

### Bước 1: Chia chunk cặp tài liệu

```bash
python scripts/process_pairs.py
```

Xuất `outputs/sample_v1_chunks.jsonl` và `outputs/sample_v2_chunks.jsonl`.

### Bước 2: So sánh v1 vs v2

```bash
python scripts/compare_pair.py
```

Xuất `outputs/comparison_report.json` với danh sách added / removed / modified.

### Bước 3 (cần GPU/HF_TOKEN): Index vào ChromaDB

```bash
python scripts/build_index.py
```

### Bước 4 (cần ChromaDB đã có dữ liệu): Tìm kiếm ngữ nghĩa

```bash
python scripts/query_chunks.py "vốn điều lệ của công ty"
```

### Kiểm tra kết quả chunking

```bash
python scripts/inspect_pairs.py
```

### Chạy test

```bash
python -m unittest tests.test_ingestion_core -v
```

## Kết quả sample hiện tại

Với cặp `sample v1.docx` và `sample v2.docx`:

- Mỗi phiên bản: `1 header`, `27 article`, `1 definition`.
- So sánh phát hiện: `4 modified`, `24 unchanged`, `0 added`, `0 removed`.

## Hướng tiếp theo

- Tích hợp LLM (Qwen2.5 qua Ollama) để tóm tắt thay đổi bằng ngôn ngữ tự nhiên.
- Làm UI Streamlit để upload tài liệu và xem báo cáo trực quan.
