# DocuMind RAG MVP

Ứng dụng RAG chạy cục bộ để tải PDF/DOCX, hỏi đáp trên tài liệu và tạo báo cáo. Giao diện React gọi FastAPI; Ollama đảm nhiệm embedding và sinh nội dung.

## Cấu trúc

```text
backend/app/     API, services, models, RAG, prompts
backend/storage/ tệp tải lên
backend/logs/    api.log, error.log
frontend/src/    pages, layouts, services và types
```

## Chạy bằng Docker

```bash
docker compose up --build
docker compose exec ollama ollama pull qwen3-embedding:0.6b
docker compose exec ollama ollama pull qwen2.5:7b
```

Mở `http://localhost:3000`. Swagger/OpenAPI tại `http://localhost:8000/docs`.

## Chạy cục bộ

Sao chép `backend/.env.example` thành `backend/.env`, khởi động Ollama, rồi cài backend. Bản demo cục bộ dùng SQLite (`rag.db`) nên chưa cần PostgreSQL hoặc Redis:

```bash
cd backend
python -m venv .venv
.venv\\Scripts\\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Trong terminal khác:

```bash
cd frontend
npm install
npm run dev
```

## API

| Method | Endpoint | Mô tả |
| --- | --- | --- |
| POST | `/documents/upload` | Upload nhiều PDF/DOCX (`files`) |
| GET | `/documents` | Danh sách tài liệu |
| DELETE | `/documents/{id}` | Xóa tệp, vector và bản ghi |
| POST | `/chat` | Hỏi đáp: `{ "question": "..." }` |
| POST | `/report` | Tạo báo cáo với `technical`, `meeting`, `research` |
| GET | `/dashboard` | Thống kê dashboard |

Mọi API nghiệp vụ trả về `{ success, message, data }`.

## Biến môi trường

`DATABASE_URL`, `OLLAMA_BASE_URL`, `LLM_MODEL`, `EMBEDDING_MODEL`, `CHROMA_DIR`, `UPLOAD_DIR`, `CHUNK_SIZE`, `CHUNK_OVERLAP`, `TOP_K` được ghi chú trong `.env.example`. Tên model không được hardcode trong mã nguồn; hãy đổi chúng tại đây.

## Sự cố thường gặp

- Không có câu trả lời: xác nhận Ollama đang chạy và đã pull cả hai model.
- Upload thất bại: chỉ nhận `.pdf` và `.docx`; PDF scan không có OCR có thể không trích được chữ.
- Backend không kết nối DB: kiểm tra `DATABASE_URL`; mặc định là SQLite (`rag.db`) ở thư mục backend.
