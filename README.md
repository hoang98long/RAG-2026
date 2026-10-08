# DocuMind RAG

Ứng dụng RAG chạy cục bộ: tải PDF/DOCX, hỏi đáp và tạo báo cáo bằng tiếng Việt. React gọi FastAPI; Ollama chạy `qwen2.5:7b` để sinh câu trả lời và một model riêng để embedding.

## Chạy cục bộ

```powershell
ollama pull qwen2.5:7b
ollama pull qwen3-embedding:0.6b
cd backend
Copy-Item .env.example .env
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
# Nếu đã có tài liệu từ phiên bản cũ, chạy trước khi khởi động API:
python -m app.reindex
uvicorn app.main:app --reload
```

Nếu đã có `.env`, cập nhật các giá trị theo `.env.example` thay vì ghi đè cấu hình riêng. Nếu dùng venv hiện có của dự án, thay `.venv` bằng `venv`. Chạy lệnh backend tại thư mục `backend` để đường dẫn SQLite, upload và Chroma đúng.

Trong terminal khác:

```powershell
cd frontend
npm install
npm run dev
```

Frontend: `http://localhost:5173`; Swagger: `http://localhost:8000/docs`. Backend dùng SQLite, không yêu cầu PostgreSQL hoặc Redis.

## Chạy bằng Docker

```bash
# Sao chép .env.example ở thư mục gốc thành .env nếu muốn tùy chỉnh.
docker compose up -d --build
docker compose exec ollama ollama pull qwen2.5:7b
docker compose exec ollama ollama pull qwen3-embedding:0.6b
# Chỉ cần nếu đã có tài liệu/chỉ mục cũ; dừng API trong lúc lập lại chỉ mục.
docker compose stop backend
docker compose run --rm backend python -m app.reindex
docker compose up -d backend
```

Mở `http://localhost:3000`. Compose truyền model và tham số RAG từ `.env` gốc; đường dẫn dữ liệu trong container được cố định riêng. Compose hiện chưa cấu hình GPU passthrough; để chạy 70B nhanh cần cấu hình GPU theo môi trường máy. Backend dùng Chroma nhúng qua `PersistentClient`; dịch vụ Chroma riêng trong Compose không được backend gọi.

## Luồng RAG và các thay đổi về độ chính xác

1. Trích PDF theo từng trang, DOCX theo nội dung văn bản; chuẩn hóa Unicode NFC và khoảng trắng, giữ xuống dòng. PDF scan vẫn cần OCR bên ngoài. Không gộp các trang trước khi chia đoạn.
2. Chia theo đoạn văn, dòng, câu rồi mới đến từ/ký tự. Lưu trang PDF (bắt đầu từ 1), vị trí và chỉ số đoạn. DOCX không có số trang ổn định nên không gán số trang.
3. Embedding theo batch, cosine similarity. Với Qwen3 embedding, chỉ truy vấn có tiền tố `Instruct: ...\nQuery: ...`; văn bản nguồn không thêm instruction. Cách dùng này theo [model card Qwen3](https://huggingface.co/Qwen/Qwen3-Embedding-4B).
4. Lấy tối đa 24 ứng viên ở mỗi nhánh: vector tìm theo ngữ nghĩa, BM25 tìm từ khóa/mã/số liệu. Hợp nhất bằng Reciprocal Rank Fusion (RRF), loại nội dung trùng chính xác, chọn tối đa 6 đoạn trong ngân sách ngữ cảnh. BM25 dùng token Unicode có dấu và IDF dương; chưa dùng bộ tách từ tiếng Việt.
5. Gửi quy tắc bằng system message, yêu cầu giữ nguyên số liệu/điều kiện, dẫn `[S1]`, `[S2]`, nêu thiếu bằng chứng và mâu thuẫn. Giao diện hiển thị mã nguồn, trang và đoạn để kiểm tra. Đây là chỉ dẫn cho mô hình; chưa có bộ kiểm chứng tự động rằng mỗi kết luận đều được nguồn hỗ trợ.

Model lớn không bù được nguồn bị trích sai hoặc truy xuất thiếu. Những cấu hình dưới đây là điểm khởi đầu, chưa phải kết quả tối ưu đã đo trên tài liệu của bạn.

## Cấu hình

| Biến | Mặc định | Ý nghĩa |
| --- | --- | --- |
| `LLM_MODEL` | `qwen2.5:7b` | Model sinh câu trả lời |
| `EMBEDDING_MODEL` | `qwen3-embedding:0.6b` | Model tạo vector, độc lập với LLM |
| `CHUNK_SIZE` | `1600` | Số ký tự Unicode tối đa mỗi đoạn, **không phải token** |
| `CHUNK_OVERLAP` | `240` | Overlap mục tiêu; phụ thuộc ranh giới đoạn, không chạy qua trang PDF |
| `TOP_K` | `6` | Số nguồn tối đa gửi LLM |
| `RETRIEVAL_CANDIDATES` | `24` | Số ứng viên tối đa mỗi nhánh, phải >= TOP_K |
| `MIN_SIMILARITY` | `0.0` | Ngưỡng cosine riêng cho nhánh vector, không loại kết quả BM25 |
| `MAX_CONTEXT_CHARS` | `14000` | Ngân sách ký tự cho nguồn và nhãn nguồn |
| `LLM_NUM_CTX` | `16384` | Cửa sổ ngữ cảnh Ollama tính bằng token |
| `LLM_NUM_PREDICT` | `2048` | Giới hạn token câu trả lời |
| `EMBEDDING_BATCH_SIZE` | `32` | Giảm nếu embedding bị thiếu bộ nhớ |
| `EMBEDDING_QUERY_INSTRUCTION` | xem `.env.example` | Mô tả nhiệm vụ truy xuất cho Qwen3 |

`temperature=0` được đặt trong code để giảm biến thiên. Cửa sổ ngữ cảnh lớn hơn tốn thêm bộ nhớ; tham khảo [Ollama context length](https://docs.ollama.com/context-length). Ngân sách ký tự chỉ là gần đúng, không đảm bảo vừa token trong mọi trường hợp; câu hỏi/yêu cầu rất dài hoặc tăng TOP_K cần điều chỉnh đồng thời các giới hạn.

Các biến đường dẫn/kết nối: `DATABASE_URL`, `OLLAMA_BASE_URL`, `CHROMA_DIR`, `UPLOAD_DIR`, `CORS_ORIGINS`; xem hai `.env.example` cho chạy từ gốc hoặc từ backend.

## Lập lại chỉ mục khi thay cấu hình

Dừng API, rồi chạy trong thư mục backend:

```powershell
python -m app.reindex
```

Lệnh đọc các bản ghi SQLite và tệp upload hiện có, tạo vector cho cấu hình mới; không cần tải lại tài liệu. Tên collection phụ thuộc phiên bản pipeline, embedding model, instruction và thông số chunking, giúp tránh trộn vector không tương thích. Collection cũ và tệp nguồn được giữ lại. Sau khi đổi các giá trị này, cần reindex toàn bộ rồi khởi động lại API; thay TOP_K/ngân sách ngữ cảnh không cần reindex.

Reindex là thao tác theo từng batch, không phải giao dịch nguyên tử toàn bộ chỉ mục. Nếu gặp lỗi giữa chừng, giữ API dừng, khắc phục rồi chạy lại; upsert cho phép chạy lại và dọn các đoạn dư. Không dùng nhiều process API cùng ghi/reindex. BM25 lưu trong RAM và dựng lại sau thay đổi qua process hiện tại; dự án hiện phù hợp một process API, cần thiết kế lại cache/tìm kiếm từ khóa khi mở rộng nhiều worker hoặc corpus lớn.

## Đo chất lượng và hướng cải thiện tiếp theo

Tạo 30–50 câu hỏi thực tế, gồm tên riêng, mã, số liệu, diễn đạt lại, so sánh nhiều trang và câu không có đáp án. Ghi câu trả lời chuẩn cùng tệp/trang chứa bằng chứng. Dùng cùng bộ câu hỏi cho mọi cấu hình, dành một phần làm tập kiểm tra độc lập.

Có thể đo retrieval bằng JSONL, mỗi dòng là một câu hỏi và các tệp bắt buộc tìm được:

```json
{"question":"Thời hạn bảo hành của thiết bị là bao lâu?", "expected_documents":["quy-dinh-bao-hanh.pdf"]}
```

```powershell
# Chạy tại backend; yêu cầu Ollama đang chạy và chỉ mục đã được tạo.
python -m app.evaluate path/to/questions.jsonl
python -m unittest discover -s tests -v
```

`app.evaluate` báo Recall@K theo tệp và MRR của tệp đúng đầu tiên, không gọi LLM. Đây chưa phải phép đo độ chính xác câu trả lời hay mức đầy đủ của từng bằng chứng: cần kiểm tra thêm đúng đoạn/trang, số liệu, điều kiện và trích dẫn. Công cụ này chỉ nhận câu có nguồn kỳ vọng; đánh giá riêng khả năng từ chối với câu không có đáp án.

Các thử nghiệm ưu tiên:

- So sánh chunk 1000/1600/2400 ký tự, overlap khoảng 15%, TOP_K 4/6/8. Không tăng đồng loạt; reindex khi đổi chunking và đo lại.
- Thử `qwen3-embedding:4b` nếu đủ RAM/VRAM: pull model, đổi EMBEDDING_MODEL, reindex. Chọn theo kết quả tài liệu tiếng Việt thực tế và độ trễ, không chỉ kích thước model. Llama 70B và embedding cạnh tranh tài nguyên nên cần đo cả thời gian tải/đổi model.
- Thêm reranker chuyên dụng khi nguồn đúng đã có trong ứng viên nhưng chưa lọt TOP_K. Hiện **chưa có reranker**; RRF chỉ hợp nhất thứ hạng hai nhánh. So sánh chất lượng trước khi thêm phụ thuộc nặng.
- Nếu tài liệu có bảng, hai cột hoặc scan: bổ sung OCR và parser giữ cấu trúc bảng/tiêu đề. Pipeline hiện tại trích văn bản thuần, có thể mất quan hệ hàng/cột.
- Nếu câu trả lời thường thiếu phần nối tiếp: thử mở rộng đoạn lân cận hoặc parent-child retrieval. Nếu tài liệu có phiên bản cũ/mới, thêm metadata ngày hiệu lực và lọc phiên bản khi truy xuất.
- Báo cáo hiện chỉ lấy TOP_K nguồn theo tiêu đề/yêu cầu, chưa tổng hợp toàn bộ corpus; báo cáo dài cần truy xuất theo từng mục và kiểm tra độ phủ. Chat hiện xử lý mỗi câu độc lập; chưa gửi lịch sử hội thoại để hiểu câu như “còn trường hợp đó thì sao?”.

## API

| Method | Endpoint | Mô tả |
| --- | --- | --- |
| POST | `/documents/upload` | Upload nhiều PDF/DOCX (`files`) |
| GET | `/documents` | Danh sách tài liệu |
| DELETE | `/documents/{id}` | Xóa tệp, vector trong cả chỉ mục cũ/mới và bản ghi |
| POST | `/chat` | Hỏi đáp: `{ "question": "..." }` |
| POST | `/report` | Tạo báo cáo với `technical`, `meeting`, `research` |
| GET | `/dashboard` | Thống kê dashboard |

API nghiệp vụ trả `{ success, message, data }`. Mỗi source có `source_id`, `document`, `document_id`, `page`, `chunk_index`, `content`, `score` và `similarity`. `score` là RRF, không phải xác suất đúng; `similarity` là cosine khi nguồn thuộc tập ứng viên vector, nếu không là null.

## Sự cố thường gặp

- Không có nguồn sau nâng cấp/đổi model: reindex theo hướng dẫn; kiểm tra đúng đường dẫn DB/Chroma/upload.
- Không sinh câu trả lời: xác nhận Ollama chạy và đã pull đúng cả hai model.
- Upload không có chữ: kiểm tra PDF scan/OCR; chỉ nhận `.pdf`, `.docx`.
- Câu trả lời bị cắt: xem LLM_NUM_PREDICT và ngân sách token còn lại.
- Nguồn sai: kiểm tra nội dung trích xuất và retrieval trước khi chỉnh prompt hoặc tăng model.

### Xử lý lỗi upload 400 và đổi model

Giao diện upload hiển thị nguyên nhân `detail` từ backend; `backend/logs/api.log` ghi lại lý do từ chối. PDF không trích được chữ có thể là bản scan/ảnh hoặc có lớp chữ lỗi. Cần OCR để tạo PDF có thể tìm kiếm văn bản rồi tải lại. Đổi model sinh câu trả lời không xử lý được bước này.

`.env.example` chỉ là tệp mẫu. Khi chạy từ thư mục `backend`, đặt `LLM_MODEL=qwen2.5:7b` trong `backend/.env` hoặc biến môi trường rồi khởi động lại backend. Upload sử dụng `EMBEDDING_MODEL`, không gọi `LLM_MODEL`.

### Mở nguồn trực tiếp từ chat

Khung hỏi đáp giữ bố cục hiện tại; nội dung tin nhắn cuộn trong khung và ô nhập luôn ở cuối. Các trích dẫn `[S1]`, `[S2]` cùng danh sách nguồn dưới từng câu trả lời và cột nguồn đều mở trang `/documents/{id}?chunk={index}&page={page}` ở tab mới.

Trang đọc hiển thị các đoạn đã lập chỉ mục theo thứ tự tài liệu, tự cuộn đến và tô nổi đoạn được dẫn. Đây là bản văn bản trích xuất, không giữ bố cục gốc; các đoạn có thể lặp phần overlap. Nút mở PDF gốc dùng `#page=` để đến trang chứa nguồn trong trình đọc PDF của trình duyệt. DOCX có nút tải bản gốc, định vị chính xác đoạn thực hiện trong bản văn bản trích xuất.

API bổ sung: `GET /documents/{id}/content` trả các đoạn đã lập chỉ mục; `GET /documents/{id}/file` trả tệp nguồn. Tài liệu không tồn tại, tệp bị xóa hoặc không có chỉ mục sẽ trả 404. Nginx trong Docker có SPA fallback để mở liên kết ở tab mới.

Kiểm tra liên kết trích dẫn ở frontend: `cd frontend` rồi `node --test tests/sources.test.mjs`.

Nguồn truy xuất được giới hạn tối đa **2 đoạn cho mỗi tài liệu**, chọn theo thứ hạng truy xuất sau khi loại nội dung trùng và kiểm tra ngân sách ngữ cảnh. Giới hạn áp dụng cho nguồn gửi mô hình và hiển thị trong chat/báo cáo. `TOP_K` vẫn giới hạn tổng số nguồn của một lần truy xuất. Thay đổi này không cần lập lại chỉ mục; chỉ cần khởi động lại backend.
