# DocuMind RAG

Ứng dụng hỏi đáp và tạo báo cáo từ PDF/DOCX bằng tiếng Việt. React gọi FastAPI; Ollama chạy `qwen2.5:7b` để trả lời, `qwen3-embedding:0.6b` để embedding. SQLite lưu nghiệp vụ; Chroma nhúng lưu vector.

## Kiến trúc truy xuất

```text
PDF/DOCX → trích trang/mục/bảng → chia đoạn theo ranh giới cấu trúc
         → tên tệp + tiêu đề mục + tiêu đề cột có trong nguồn
         → contextual embedding + contextual BM25
Câu hỏi  → vector + BM25 → RRF → reranking → tối đa 2 đoạn/tài liệu
         → TOP_K + ngân sách ngữ cảnh → sinh câu trả lời → kiểm tra mã trích dẫn
```

- PDF giữ trang từ 1, nhận diện tiêu đề Điều/Chương/Mục/Phần và các tiêu đề Article/Chapter/Section có số. DOCX đọc thân tài liệu theo thứ tự đoạn văn/bảng, giữ các ô cùng hàng và lặp tiêu đề cột khi hàng được đánh dấu header trong tệp. Không đoán hàng đầu tiên là tiêu đề.
- Chunk không cắt xuyên qua trang hoặc mục đã nhận diện. Kích thước và overlap tính bằng **ký tự Unicode**, không phải token; overlap là mục tiêu và chỉ áp dụng trong cùng khối.
- Tên tệp, tiêu đề mục và tiêu đề cột nguồn được thêm vào văn bản dùng cho cả embedding/BM25. Chroma vẫn lưu nguyên đoạn nguồn để hiển thị và dẫn chứng. Đây là bổ sung ngữ cảnh theo metadata, **không phải** bản triển khai đầy đủ Contextual Retrieval sinh ngữ cảnh bằng LLM.
- RRF hợp nhất hai nhánh. Reranker đánh giá lại ứng viên trước khi chọn nguồn. Mặc định dùng Ollama hiện có, không tải model khác; có lựa chọn cross-encoder BGE riêng.
- Tối đa **2 đoạn cho mỗi tài liệu** theo thứ hạng sau reranking, rồi giới hạn tổng `TOP_K` và ngân sách ký tự. Không phải hai đoạn đầu theo thứ tự trong tệp.
- Generation yêu cầu dẫn `[S1]`, `[S2]`, giữ số liệu/điều kiện và nêu mâu thuẫn. Code kiểm tra mã trích dẫn; cho sửa một lần nếu thiếu/sai mã, rồi từ chối nếu vẫn lỗi. Bộ kiểm tra này **chưa kiểm chứng ngữ nghĩa** từng kết luận và chưa bảo đảm mọi kết luận đều có bằng chứng.

Cơ sở nghiên cứu, lựa chọn mô hình và giới hạn: [docs/RAG_ACCURACY.md](docs/RAG_ACCURACY.md). Chưa có benchmark câu hỏi thực tế của người dùng; không quy đổi các kiểm thử phần mềm thành tỷ lệ cải thiện độ chính xác.

## Chạy cục bộ

```powershell
ollama pull qwen2.5:7b
ollama pull qwen3-embedding:0.6b
cd backend
Copy-Item .env.example .env
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
# Sau nâng cấp pipeline này hoặc khi đổi embedding/chunking:
python -m app.reindex
uvicorn app.main:app --reload
```

Nếu đã có `.env`, cập nhật các biến thay vì ghi đè cấu hình riêng. Nếu dùng môi trường hiện có, thay `.venv` bằng `venv`. Lệnh backend chạy tại thư mục `backend` để SQLite/Chroma/upload có đường dẫn đúng. `.env.example` chỉ là mẫu, không được ứng dụng tự đọc.

Trong terminal khác: `cd frontend`, `npm install`, `npm run dev`. Frontend: `http://localhost:5173`; Swagger: `http://localhost:8000/docs`.

## Docker

```bash
# Có thể sao chép .env.example gốc thành .env để cấu hình Compose.
docker compose up -d --build
docker compose exec ollama ollama pull qwen2.5:7b
docker compose exec ollama ollama pull qwen3-embedding:0.6b
docker compose stop backend
docker compose run --rm backend python -m app.reindex
docker compose up -d backend
```

Mở `http://localhost:3000`. Compose chưa cấu hình GPU passthrough. Backend dùng Chroma nhúng, không gọi dịch vụ Chroma riêng trong Compose. Nginx có SPA fallback để mở link nguồn ở tab mới. Cross-encoder không nằm trong image mặc định; nếu bật cần thêm `requirements-reranker.txt` vào bước cài dependency của image. Có thể đặt ngưỡng cross-encoder bằng environment override trong Compose, sau khi đã đo/calibrate.

## Cấu hình

| Biến | Mặc định | Ý nghĩa |
| --- | --- | --- |
| `LLM_MODEL` | `qwen2.5:7b` | Model sinh câu trả lời |
| `EMBEDDING_MODEL` | `qwen3-embedding:0.6b` | Embedding, độc lập với LLM |
| `CHUNK_SIZE`, `CHUNK_OVERLAP` | `1600`, `240` | Ký tự Unicode |
| `TOP_K` | `6` | Tổng số đoạn nguồn tối đa; mỗi tài liệu tối đa 2 |
| `RETRIEVAL_CANDIDATES` | `48` | Ứng viên mỗi nhánh vector/BM25 |
| `MIN_SIMILARITY` | `0.0` | Ngưỡng cosine riêng cho vector; BM25 vẫn có thể giữ nguồn |
| `MAX_CONTEXT_CHARS` | `14000` | Ngân sách ký tự nguồn và nhãn |
| `LLM_NUM_CTX`, `LLM_NUM_PREDICT` | `16384`, `2048` | Token ngữ cảnh/đầu ra Ollama |
| `EMBEDDING_BATCH_SIZE` | `32` | Batch embedding |
| `RERANK_BACKEND` | `ollama` | `off`, `ollama`, `cross_encoder` |
| `RERANK_MODEL` | rỗng | Ollama dùng LLM_MODEL khi để rỗng |
| `RERANK_CANDIDATES` | `32` | Số ứng viên RRF đầu tiên được chấm lại |
| `RERANK_BATCH_SIZE` | `6` | Batch chấm điểm |
| `RERANK_MIN_GRADE` | `2` | Ollama: giữ bằng chứng một phần/trực tiếp; thang 0–3 |
| `RERANK_TIMEOUT` | `120` | Timeout giây của client Ollama cho từng batch; nhiều batch làm tổng thời gian dài hơn |
| `CROSS_ENCODER_MODEL` | `BAAI/bge-reranker-v2-m3` | Model chuyên chấm cặp query/passage |
| `CROSS_ENCODER_DEVICE` | `cpu` | Có thể đổi sang `cuda` khi PyTorch/GPU hỗ trợ |
| `CROSS_ENCODER_MAX_LENGTH` | `1024` | Token tối đa mỗi cặp, đoạn dài có thể bị cắt |
| `CROSS_ENCODER_MIN_SCORE` | không đặt | Chỉ đặt sau khi calibrate trên bộ câu hỏi có nhãn |
| `CITATION_REPAIR` | `true` | Sửa một lần nếu mã trích dẫn thiếu/không hợp lệ |

Grade Ollama: 0 không liên quan, 1 chỉ cùng chủ đề, 2 bằng chứng một phần, 3 trực tiếp. Không phải xác suất đúng; không dùng chung ngưỡng với score của cross-encoder. Nếu reranker lỗi/timeout hoặc trả ID không hợp lệ, code log cảnh báo và dùng lại thứ hạng hybrid, kèm `rerank_method=hybrid_fallback`. Trong trạng thái này không có bộ lọc grade, nên vẫn có thể trả nguồn không đủ liên quan.

`temperature=0`; ngân sách ký tự chỉ gần đúng với token. Cửa sổ lớn hơn dùng thêm bộ nhớ; tham khảo [Ollama context length](https://docs.ollama.com/context-length). Các biến kết nối/đường dẫn trong `.env.example`: `DATABASE_URL`, `OLLAMA_BASE_URL`, `CHROMA_DIR`, `UPLOAD_DIR`, `CORS_ORIGINS`, `EMBEDDING_QUERY_INSTRUCTION`.

Để thử BGE khi đủ tài nguyên:

```powershell
cd backend
pip install -r requirements-reranker.txt
# Trong backend/.env: RERANK_BACKEND=cross_encoder
# Khởi động lại backend; lần đầu tải model từ Hugging Face.
```

Chưa cài dependency/model BGE tự động. Model và PyTorch chiếm thêm bộ nhớ/dung lượng. Nếu cần tốc độ trước, đặt `RERANK_BACKEND=off` để so sánh với hybrid baseline.

## Lập lại chỉ mục

Dừng API, chạy `python -m app.reindex` tại thư mục backend. Pipeline này dùng collection `documents_v4_*`; collection v2/cũ và tệp upload được giữ nguyên. Tên collection phụ thuộc phiên bản pipeline, model embedding, instruction và chunking. **Cần reindex sau nâng cấp này**, thay embedding/instruction/chunking; thay reranker/LLM/TOP_K không cần reindex.

Reindex đọc DB và tệp đã upload, upsert từng batch; không phải giao dịch nguyên tử toàn corpus. Nếu lỗi, giữ API dừng, khắc phục và chạy lại rồi mới mở API. Không dùng nhiều process cùng ghi/reindex. BM25 hiện dùng SQLite FTS5 trên đĩa; truy vấn chỉ đọc văn bản của tập ứng viên. API xóa tài liệu dọn cả collection cũ/v2/v3/v4 để đổi cấu hình không khôi phục nguồn đã xóa.

## Đo độ chính xác và so sánh phương pháp

Tạo 30–50 câu hỏi thực tế có bằng chứng chuẩn, gồm mã, số liệu, câu diễn đạt lại, so sánh và câu không có đáp án. Dành tập kiểm tra độc lập, tránh chọn tham số dựa vào chính tập này.

JSONL hỗ trợ nhãn tệp như phiên bản cũ hoặc nhãn trang/đoạn:

```json
{"question":"Thời hạn bảo hành của AB987?", "expected_sources":[{"document":"bao-hanh.pdf", "page":3, "chunk_index":4}]}
{"question":"Điều kiện loại trừ là gì?", "expected_documents":["bao-hanh.pdf"]}
{"question":"Tài liệu không có câu trả lời cho câu này", "expected_sources":[]}
```

`document_id` có thể thay hoặc bổ sung `document`, giúp phân biệt hai upload trùng tên. Trang từ 1, chunk_index từ 0. Có thể bỏ chunk_index để chỉ đánh giá đúng trang. Sau đổi chunking/reindex phải rà lại nhãn chunk_index. Danh sách rỗng là câu không có nguồn phù hợp.

```powershell
cd backend
python -m app.evaluate path/to/questions.jsonl --hybrid-only --output evaluation/hybrid.json
python -m app.evaluate path/to/questions.jsonl --output evaluation/reranked.json
python -m unittest discover -s tests -v
```

Công cụ báo recall, precision trên các nguồn trả về, MRR, khả năng không trả nguồn ở câu không có đáp án, thời gian trung bình/p95 và số ca fallback. File JSON lưu cấu hình, nhãn và nguồn để kiểm tra lỗi. **Chỉ đo retrieval**, không gọi model sinh câu trả lời, không đo hallucination hoặc chất lượng câu trả lời. Chạy warm-up trước nếu muốn loại ảnh hưởng tải model; lưu cùng dataset cho cả hai cấu hình.

## Giới hạn và thử nghiệm tiếp theo

- PDF scan cần OCR bên ngoài. Parser PDF văn bản chưa giữ quan hệ bảng/hai cột; parser DOCX mới xử lý thân tài liệu, chưa đầy đủ header/footer, chú thích, bảng lồng và lịch sử sửa đổi.
- Nhận diện mục PDF dựa quy tắc, có thể bỏ sót tiêu đề hoặc nhận diện nhầm; không tự suy ra ngày hiệu lực/phiên bản.
- Chat vẫn hỏi từng câu độc lập; chưa giải quyết câu hỏi nối tiếp bằng lịch sử. Báo cáo chỉ truy xuất theo tiêu đề/yêu cầu, chưa kiểm tra độ phủ toàn corpus.
- Giới hạn 2 đoạn/tài liệu có thể thiếu bằng chứng cho câu hỏi nhiều điều kiện nằm rải rác; cần đo trước khi thêm parent-child retrieval/đoạn lân cận.
- Thử `qwen3-embedding:4b` nếu đủ RAM/VRAM, reindex và đo với cùng tập câu hỏi. Chưa đổi mặc định vì chưa có dữ liệu phần cứng hoặc benchmark chứng minh bản lớn phù hợp hơn.
- Bước kiểm tra mã trích dẫn không xác nhận nội dung trích dẫn đúng. Cần thêm đánh giá thủ công hoặc kiểm chứng kết luận/bằng chứng cho các trường hợp quan trọng.

## API và giao diện

API nghiệp vụ trả `{ success, message, data }`.

| Method | Endpoint | Chức năng |
| --- | --- | --- |
| POST | `/documents/upload` | PDF/DOCX, nhiều tệp qua `files` |
| GET | `/documents/paged` | Danh sách phân trang (`offset`, `limit`) |
| GET | `/documents/upload-limits` | Giới hạn tải lên hiện tại |
| GET | `/documents` | Danh sách |
| DELETE | `/documents/{id}` | Xóa tài liệu |
| GET | `/documents/{id}/file` | Mở/tải bản gốc |
| GET | `/documents/{id}/content` | Đoạn đã lập chỉ mục theo thứ tự |
| POST | `/chat` | `{ "question": "..." }` |
| POST | `/report` | Mẫu `technical`, `meeting`, `research` |
| GET | `/dashboard` | Thống kê |

Source có mã `source_id`, tên/ID tài liệu, trang, chỉ số đoạn, nội dung, section/table_header và điểm truy xuất/rerank khi có. Không coi điểm là xác suất trả lời đúng.

Khung chat cuộn nội dung, giữ ô nhập ở cuối. Trích dẫn và nguồn mở tab mới, cuộn/tô nổi đoạn trong bản văn bản trích xuất. PDF gốc mở qua `#page=`; DOCX có nút tải bản gốc. Bản trích xuất không giữ bố cục gốc và có thể lặp overlap. Kiểm thử liên kết: tại frontend chạy `node --test tests/sources.test.mjs`.

## Sự cố thường gặp

- Upload 400: giao diện hiện `detail`, log `backend/logs/api.log` ghi nguyên nhân. PDF scan/lớp chữ lỗi cần OCR; PDF khóa/hỏng cần xuất lại bản đọc được. Upload dùng embedding, không gọi LLM.
- Không có nguồn sau nâng cấp: reindex v4 và kiểm tra đúng DB/Chroma/upload.
- Không kết nối Ollama: khởi động dịch vụ, pull cả LLM/embedding; xem `OLLAMA_BASE_URL`.
- Reranking chậm: giảm batch/ứng viên, so sánh `off` hoặc thử cross-encoder. Đổi model không thể được coi là cải thiện nếu chưa đo.
- Nguồn bị lọc hết: kiểm tra nhãn bằng chứng/grade và dataset trước khi hạ ngưỡng; đừng coi mọi đoạn cùng chủ đề là bằng chứng.

## Nâng cấp cho nhiều tài liệu và tệp lớn

- Mặc định **200 MiB/tệp**, **512 MiB/yêu cầu multipart**, **20 tệp/yêu cầu API**. Giao diện có thể chọn nhiều tệp hơn và gửi từng tệp lần lượt, nên không gom toàn bộ danh sách vào một request lớn. Tệp đã thành công được bỏ khỏi danh sách chờ; nếu tệp sau lỗi, các tệp đã lưu được giữ lại.
- Các giới hạn cấu hình trong `.env`: `UPLOAD_MAX_FILE_MB`, `UPLOAD_MAX_REQUEST_MB`, `UPLOAD_MAX_FILES`. `GET /documents/upload-limits` cung cấp giới hạn cho giao diện. Middleware chặn tổng raw body cả khi không có Content-Length; service kiểm tra dung lượng từng tệp khi sao chép theo khối 1 MiB.
- PDF đọc/trích văn bản từng trang; DOCX đọc XML từng đoạn/hàng, giải phóng các phần đã xử lý và chia các khối văn bản dài theo cửa sổ. Embedding chỉ giữ một batch. Bộ phân tích PDF vẫn có thể dùng nhiều RAM cho cấu trúc/tài nguyên của một tệp; đây không phải bảo đảm bộ nhớ hằng số cho mọi PDF.
- BM25 chuyển từ danh sách Python trong RAM sang **SQLite FTS5**, có index document/chunk và trigger giữ dữ liệu tìm kiếm đồng bộ. Dữ liệu nằm trong `CHROMA_DIR/lexical/`; cần sao lưu thư mục này cùng Chroma. Unicode giữ dấu tiếng Việt. Thứ hạng FTS5 có thể khác BM25 cũ, cần chạy lại evaluation.
- `INDEX_PAGE_SIZE=500` giới hạn số chunk mỗi lần đọc khi phục hồi chỉ mục từ khóa. Dấu dirty và kiểm tra số lượng phát hiện thao tác ghi bị gián đoạn; lần truy xuất tiếp theo có thể dựng lại FTS theo từng trang. Có thể dựng trước bằng `python -m app.reindex --lexical-only`, không gọi Ollama.
- Reader tải **50 đoạn/lần**, API tối đa 200; link nguồn tự tải phần chứa chunk/trang mục tiêu. Có nút phần trước/tiếp, không tạo DOM cho toàn tài liệu. API content nhận `offset`, `limit`, `chunk`, `page` và trả thêm `total`, `offset`, `limit`, `target_found`.
- Tăng phạm vi tìm kiếm lên **48 ứng viên mỗi nhánh**, chấm lại **32 ứng viên RRF** để giảm nguy cơ bỏ sót khi corpus lớn. Vẫn tối đa 2 đoạn/tài liệu, TOP_K=6 và ngân sách ngữ cảnh cũ. Reranking nhiều hơn tốn thêm thời gian; đánh giá recall/precision/độ trễ trước khi tăng tiếp.

**Cần reindex vào v4** vì cửa sổ trích xuất DOCX và phương pháp lexical đã thay đổi. Chỉ mục cũ và tệp upload được giữ nguyên. Dừng backend, cập nhật `.env` rồi chạy tại backend: `python -m app.reindex`, sau đó khởi động lại API. `--lexical-only` không thay cho reindex toàn bộ khi chuyển v3 → v4.

Nginx có `client_max_body_size 512m` và thời gian chờ nhận body 300 giây. Nếu tăng giới hạn request, cần chỉnh Nginx/reverse proxy tương ứng. API upload vẫn xử lý đồng bộ tới khi embedding xong; giao diện chờ kết quả và gửi tuần tự, chưa có hàng đợi công việc bền vững hay resume upload sau khi đóng trình duyệt. Trong một request API nhiều tệp, lỗi làm rollback cả request; các request đã hoàn tất trước đó không bị rollback.

Không đặt trần tổng số tài liệu trong ứng dụng. Sức chứa thực tế phụ thuộc ổ đĩa, RAM của index vector Chroma và tài nguyên Ollama; chưa có benchmark chứng minh số lượng tối đa hoặc độ chính xác trên corpus lớn thực tế. Tiếp tục dùng một process ghi chỉ mục, dừng API khi reindex. FTS5 giảm tải văn bản trong RAM, không làm index vector hay embedding trở thành không giới hạn tài nguyên. Khi cần nhiều tiến trình ghi hoặc nhiều người upload đồng thời, cần hàng đợi worker và dịch vụ vector riêng.

Cơ chế tìm kiếm toàn văn và BM25 trên đĩa dựa theo [SQLite FTS5](https://www.sqlite.org/fts5.html). Kiểm thử mở rộng dùng dữ liệu tổng hợp và embedding giả để xác minh batch, phân trang, tính nhất quán; không dùng kết quả đó thay cho benchmark độ chính xác với model thật.

Danh sách tài liệu trong trang quản lý và cột chat phân trang 50 tệp, qua API `GET /documents/paged?offset=0&limit=50` (tối đa 200). API `/documents` cũ vẫn giữ để tương thích.

## Lưu trữ riêng trên từng máy triển khai

Database, Chroma/FTS, tài liệu upload và `.env` riêng được ignore; Docker build cũng không đóng gói dữ liệu máy phát triển. Giữ nguyên đường dẫn và volume trên máy đã ingest. **Lần pull đầu commit bỏ theo dõi dữ liệu cần sao lưu/khôi phục trước khi chạy lại backend**, vì Git có thể xóa các tệp cũ đang tracked. Xem [hướng dẫn cập nhật giữ dữ liệu](docs/STORAGE_DEPLOYMENT.md).

Giao diện chat ẩn mã trích dẫn nội bộ `[S1]`, `[S1, S2]` trong phần trả lời. Nguồn tham chiếu vẫn hiển thị tên tệp, trang/đoạn và link mở đúng vị trí; backend vẫn giữ mã để kiểm tra trích dẫn.
