# DocuMind RAG

Hỏi đáp và tạo báo cáo từ PDF/DOCX bằng tiếng Việt. FastAPI + React, SQLite lưu metadata/lịch sử, Chroma nhúng lưu vector và SQLite FTS5 lưu chỉ mục từ khóa. Mặc định chat bằng `qwen2.5:7b`; có thêm `llama3.1:70b` và OpenAI API.

## Hai kho tài liệu độc lập

Upload chọn **Nội bộ** hoặc **Public**. Mỗi kho có DB metadata, tệp gốc, vector và lexical index riêng. Dữ liệu đã ingest từ trước giữ nguyên là nội bộ; không tự copy hay chuyển vào public.

| Mô hình | Kho được chọn | Gửi bằng chứng qua OpenAI |
| --- | --- | --- |
| `qwen2.5:7b`, `llama3.1:70b` | Nội bộ, public hoặc cả hai | Không |
| OpenAI (`OPENAI_MODEL`) | Chỉ public | Chỉ nội dung public |

Backend chặn OpenAI với `scope=private/all` trước retrieval; không fallback về dữ liệu nội bộ. `OPENAI_API_KEY=` để trống trong mẫu, chỉ điền tại `.env` backend khi muốn bật. Giao diện chỉ biết trạng thái cấu hình, không nhận key. **Embedding của cả hai kho vẫn chạy qua Ollama**: ingest public không cần key, local đọc vector public không gọi OpenAI. Phân hệ tách dữ liệu/LLM, chưa tách runtime embedding khỏi Ollama.

Chi tiết cách triển khai, ranh giới bảo mật và giới hạn: [PUBLIC_PRIVATE_RAG.md](docs/PUBLIC_PRIVATE_RAG.md).

## Quyền truy cập khi phục vụ người dùng bên ngoài

Chưa đăng nhập chỉ xem/hỏi public. Private/all, upload, xóa và báo cáo cần khóa `INTERNAL_ACCESS_TOKEN` trong `.env` backend (hoặc `.env` gốc khi chạy Compose). Khóa để trống thì các chức năng này bị khóa. Dùng nút **Đăng nhập nội bộ**; khóa không được lưu trong storage trình duyệt. Production cần HTTPS, `SESSION_COOKIE_SECURE=true`, `CORS_ORIGINS` đúng tên miền. Xem [cấu hình quyền và triển khai](docs/PUBLIC_PRIVATE_RAG.md#truy-cập-từ-bên-ngoài-quyền-public-và-quyền-nội-bộ).

Frontend mặc định dùng `/api` cùng origin: Vite proxy khi phát triển, Nginx proxy khi chạy Docker. Các cổng backend/Ollama/Chroma chỉ bind loopback; service Chroma cũ chuyển sang profile tùy chọn vì backend dùng Chroma nhúng. Giữ nguyên volumes và không ingest lại nếu đã dùng v5.

## Pipeline chat v5

```text
PDF/DOCX → trích trang/mục/phụ lục/bảng → chia đoạn theo cấu trúc
         → thêm tên tệp/tiêu đề có trong nguồn → embedding Ollama + FTS5
Câu hỏi  → câu gốc + diễn đạt lại/tách điều kiện → dense + lexical → RRF
         → truy vấn bổ sung từ nguồn → rerank → đoạn lân cận/mục/phụ lục
         → giới hạn ngữ cảnh → trả lời → kiểm tra mã + đối chiếu bằng chứng
```

- Nhận diện Điều/Chương/Mục/Phần/Phụ lục và heading tiếng Anh có số/Roman. Chunks giữ trang PDF từ 1, chỉ số đoạn từ 0; DOCX giữ hàng bảng và header được đánh dấu. Không tự đoán số hiệu văn bản hay phụ lục dựa trên kiến thức ngoài nguồn.
- Chunk và overlap tính bằng **ký tự Unicode**, không phải token. Không cắt xuyên trang hoặc khối mục; PDF vẫn có thể bị trích sai khi là scan, bảng/hai cột.
- Planner giữ câu gốc, tối đa 3 truy vấn diễn đạt lại và 2 truy vấn bổ sung. Planner lỗi giữ retrieval gốc. Có thể nối bằng chứng của nhiều tài liệu trong kho được phép.
- Bổ sung đoạn lân cận; câu hỏi danh sách/toàn bộ mở rộng mục của nguồn và theo tham chiếu phụ lục trong cùng tệp qua các trang. “Phụ lục I/01” có khóa chuẩn hóa chung. Mục con có thể vẫn làm tách phạm vi phụ lục; không bảo đảm parser nhận diện mọi cấu trúc.
- **Hai nguồn/tài liệu là giới hạn hiển thị trong chat**, không chặn lượng bằng chứng dùng trả lời. Link ưu tiên các đoạn thực sự được câu trả lời dẫn. Với danh sách dài, chúng là các link đại diện, không hiển thị toàn bộ bằng chứng. API retrieval baseline vẫn dùng TOP_K/2 đoạn; báo cáo truy xuất và kiểm chứng theo từng mục, với hai nguồn đại diện mỗi tài liệu khi hiển thị.
- Kiểm tra record metadata và tệp gốc của đúng kho trước khi dùng đoạn ứng viên; loại nguồn còn sót do upload lỗi, tệp đã mất hoặc đường dẫn sai kho. Không quét toàn bộ danh mục và không tự xóa dữ liệu.
- Ưu tiên phụ lục được hỏi/tham chiếu trước phần mở rộng mục chung. Coverage ghi số đoạn thực sự giữ trong ngữ cảnh và cảnh báo khi thiếu phụ lục, kể cả câu hỏi không yêu cầu liệt kê toàn bộ.
- Kiểm tra mã nguồn, thêm reviewer đối chiếu từng dòng kết luận với đoạn được dẫn và trích đoạn nguyên văn; sửa tối đa một lần, từ chối trả lời nếu vẫn sai hoặc không kiểm chứng được. Reviewer vẫn có thể sai; chưa thay cho đánh giá thủ công.
- MMR chọn pool trước rerank để hạn chế đoạn gần trùng; nội dung mở rộng lấy luân phiên giữa các tài liệu/mục cùng mức ưu tiên. CLI có `--no-diversity` và `complete_evidence_rate` để đo đối chứng; xem [nghiên cứu thuật toán](docs/RAG_ACCURACY.md#rà-soát-thuật-toán-mmr-và-phân-bổ-ngữ-cảnh).
- Khi chưa đọc hết phạm vi/ngữ cảnh bị cắt, `coverage` và giao diện báo kết quả có thể thiếu. Không trình bày đầu ra bị model cắt như một danh sách hoàn chỉnh.
- Mã `[S1]`, `[S1, S2]` được ẩn trong câu trả lời hiển thị. Nguồn vẫn có tên tệp/trang/đoạn và link mở đúng phần. Link chứa kho, version và hash nội dung; trả 409 nếu đã reindex/đổi đoạn, tránh mở nhầm nguồn cũ. PDF gốc mở qua `#page=`; đây là thứ tự trang trong tệp, không phải số trang in trên giấy.

Những cải thiện này dựa trên các vấn đề trong `note.docx`. Chưa có benchmark trên bộ tài liệu/câu hỏi thực tế của người dùng, nên chưa có tỷ lệ cải thiện accuracy. Nghiên cứu nền: [RAG_ACCURACY.md](docs/RAG_ACCURACY.md).

## Triển khai thử nghiệm

Làm theo [PILOT_DEPLOYMENT.md](docs/PILOT_DEPLOYMENT.md) để cấu hình quyền, kiểm tra trước triển khai, nghiệm thu public/private, đo chất lượng và chuẩn bị rollback. Có thêm `/ready`, trạng thái model thực tế và `python -m app.preflight --scope all` để phát hiện vấn đề cấu hình/lưu trữ mà không tự sửa dữ liệu.

## Chạy cục bộ

Tại thư mục backend, giữ `.env` đã có; chỉ tạo mẫu cho máy mới:

```powershell
ollama pull qwen2.5:7b
ollama pull qwen3-embedding:0.6b
# Chỉ cần khi chọn Llama, máy phải có đủ RAM/VRAM:
# ollama pull llama3.1:70b
cd backend
if (-not (Test-Path -LiteralPath '.env')) { Copy-Item .env.example .env }
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
# Chỉ migration v4 → v5 / đổi embedding hoặc chunking, sau backup và dừng API:
# python -m app.reindex --scope private
# Chỉ khi kho public đã có tài liệu cần chuyển pipeline:
# python -m app.reindex --scope public
uvicorn app.main:app --reload
```

Nếu dùng môi trường có sẵn, thay `.venv` bằng `venv`. Chạy backend tại thư mục `backend` để đường dẫn tương đối đúng. `.env.example` chỉ là mẫu, ứng dụng đọc `.env`. Điền key và khởi động lại backend để bật OpenAI; không đặt key vào biến `VITE_*`.

Terminal frontend: `cd frontend`, `npm ci`, `npm run dev`. Frontend `http://localhost:5173`; Swagger `http://localhost:8000/docs`.

## Docker

```bash
docker compose up -d --build
docker compose exec ollama ollama pull qwen2.5:7b
docker compose exec ollama ollama pull qwen3-embedding:0.6b
# Không reindex khi cập nhật thông thường; xem quy trình migration bên dưới.
```

Giao diện `http://localhost:3000`. Compose giữ volume private cũ, thêm `public_chroma_data`; DB/upload public ở `/app/storage/public` trong volume `uploads`. Key/cấu hình Compose dùng `.env` gốc. Không đổi project/volume và không dùng `docker compose down -v` khi cập nhật. Chưa cấu hình GPU passthrough. Backend dùng Chroma nhúng, không gọi dịch vụ Chroma riêng trong Compose. Cross-encoder không nằm trong image mặc định, nếu bật cần cài dependency của nó.

## Tổng hợp và viết báo cáo

Báo cáo dùng dàn ý tối đa 4 mục, truy xuất riêng từng mục và kiểm chứng bằng chứng trước khi ghép bài. Có thể chọn Qwen/Llama, chọn tối đa 20 tài liệu nội bộ và nhập dàn ý riêng. Giao diện báo phần còn thiếu, giữ yêu cầu khi lỗi và xuất Markdown không hiện mã S trong prose. Chi tiết phương pháp, nghiên cứu đã đối chiếu và giới hạn: [REPORT_RAG.md](docs/REPORT_RAG.md). Nâng cấp này giữ chỉ mục v5, không cần reindex.

## Cấu hình chính

Giữ nguyên `DATABASE_URL`, `CHROMA_DIR`, `UPLOAD_DIR` trên máy đã ingest. Các đường dẫn mặc định bên dưới tính từ thư mục backend; settings từ chối đường dẫn private/public chồng nhau.

| Biến | Mặc định | Ý nghĩa |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///./rag.db` | DB nội bộ hiện có |
| `CHROMA_DIR`, `UPLOAD_DIR` | `./chroma_data`, `./storage/uploads` | Index và tệp nội bộ |
| `PUBLIC_DATABASE_URL` | `sqlite:///./storage/public/public.db` | DB public riêng |
| `PUBLIC_CHROMA_DIR`, `PUBLIC_UPLOAD_DIR` | `./public_chroma_data`, `./storage/public/uploads` | Index và tệp public |
| `OPENAI_API_KEY` | trống | Chỉ backend đọc key |
| `INTERNAL_ACCESS_TOKEN` | trống | Khóa ngẫu nhiên 32–512 ký tự để mở quyền nội bộ |
| `SESSION_COOKIE_SECURE`, `SESSION_MAX_AGE` | `false`, `14400` | Đặt secure=true khi triển khai HTTPS |
| `PUBLIC_CHAT_RATE_LIMIT`, `PUBLIC_CHAT_MAX_CONCURRENT` | `20`, `2` | Hạn mức/phút/IP và số câu xử lý đồng thời khi chưa đăng nhập |
| `OPENAI_MODEL` | `gpt-4.1-mini` | Model cho lựa chọn OpenAI |
| `OPENAI_TIMEOUT` | `90` | Timeout giây mỗi request API |
| `EMBEDDING_MODEL` | `qwen3-embedding:0.6b` | Embedding qua Ollama cho hai kho riêng |
| `CHUNK_SIZE`, `CHUNK_OVERLAP` | `1600`, `240` | Ký tự Unicode |
| `TOP_K` | `6` | Baseline; chat mở rộng tối đa 2 × TOP_K anchor |
| `RETRIEVAL_CANDIDATES` | `48` | Ứng viên mỗi nhánh/truy vấn |
| `RERANK_BACKEND` | `ollama` | `off`, `ollama`, `cross_encoder`; OpenAI dùng public grader khi bật rerank |
| `RERANK_CANDIDATES`, `RERANK_BATCH_SIZE` | `32`, `6` | Phạm vi/batch rerank |
| `RERANK_DIVERSITY_LAMBDA` | `0.75` | MMR trước rerank; 1 giữ top pool cũ |
| `RERANK_MIN_GRADE`, `RERANK_TIMEOUT` | `2`, `120` | Grade 0–3; timeout mỗi batch Ollama |
| `QUERY_EXPANSION`, `GROUNDING_VERIFICATION` | `true`, `true` | Diễn đạt lại/truy xuất bổ sung và reviewer |
| `NEIGHBOR_CHUNKS` | `1` | Số đoạn lân cận mỗi phía |
| `MAX_CONTEXT_CHARS` | `14000` | Ngân sách bằng chứng câu hỏi thường |
| `EXHAUSTIVE_CONTEXT_CHARS`, `EVIDENCE_MAX_CHUNKS` | `32000`, `80` | Ngân sách cho danh sách dài |
| `LLM_NUM_CTX`, `LLM_NUM_PREDICT` | `16384`, `2048` | Cửa sổ Ollama và đầu ra thường |
| `EXHAUSTIVE_NUM_PREDICT` | `4096` | Đầu ra cho câu hỏi danh sách |
| `EMBEDDING_BATCH_SIZE`, `INDEX_PAGE_SIZE` | `32`, `500` | Batch embedding và phục hồi lexical |
| `UPLOAD_MAX_FILE_MB`, `UPLOAD_MAX_REQUEST_MB`, `UPLOAD_MAX_FILES` | `200`, `512`, `20` | MiB/tệp, MiB/request, tệp/request API |

Điểm cosine/BM25/RRF/grade không phải xác suất trả lời đúng. Reranker lỗi giữ thứ hạng hybrid và báo `hybrid_fallback`; reviewer lỗi không xuất câu trả lời. Mỗi bước tăng thời gian xử lý/chi phí; so sánh bằng bộ câu hỏi có nhãn trước khi thay ngưỡng. Ngân sách ký tự không đo chính xác token.

BGE tùy chọn: cài `pip install -r requirements-reranker.txt`, đặt `RERANK_BACKEND=cross_encoder`, `CROSS_ENCODER_MODEL=BAAI/bge-reranker-v2-m3`, device `cpu` hoặc `cuda`. Ngưỡng `CROSS_ENCODER_MIN_SCORE` chỉ đặt sau khi hiệu chỉnh trên dữ liệu có nhãn. Đổi embedding sang bản lớn hơn chỉ khi đủ tài nguyên và đã đo, cần reindex.

## Lưu trữ, cập nhật và reindex

Database, SQLite WAL/SHM/journal, Chroma/FTS, upload, log và `.env` riêng được Git ignore. Docker build cũng loại dữ liệu máy phát triển. **Lần pull đầu tiên commit bỏ tracking dữ liệu cần sao lưu/khôi phục**, vì Git có thể xóa tệp cũ đang tracked: [STORAGE_DEPLOYMENT.md](docs/STORAGE_DEPLOYMENT.md).

Pipeline hiện tại tạo collection `documents_v5_*`; tên phụ thuộc model/instruction/chunking. Giữ collection cũ và tệp đã upload, không tự chuyển dữ liệu. Reindex từng kho trên chính máy triển khai khi nâng cấp v4 → v5 hoặc đổi embedding/chunking/instruction. Đổi LLM/reranker không cần reindex.

Dừng API và mọi process ghi, backup toàn bộ DB/index/upload, chạy `python -m app.reindex --scope private` hoặc `public`, rồi khởi động lại. Không phải giao dịch nguyên tử toàn corpus; nếu lỗi, giữ API dừng, khắc phục rồi chạy lại. `--lexical-only` chỉ dựng FTS từ vector hiện tại, không chuyển pipeline cũ. Không dùng nhiều process cùng ghi Chroma nhúng. Xóa tài liệu dọn các collection của riêng kho được chọn, không xóa kho còn lại.

PDF đọc từng trang, DOCX theo đoạn/hàng XML, embedding theo batch. FTS5 trên đĩa không tải toàn corpus vào RAM khi query. Reader và danh sách tải 50 mục/lần, API tối đa 200. Giao diện gửi từng tệp tuần tự; tệp đã thành công giữ lại nếu tệp sau lỗi. Upload API vẫn đồng bộ tới khi embedding xong, chưa có queue bền vững/resume. Parser PDF và vector index vẫn có thể dùng nhiều RAM; sức chứa phụ thuộc phần cứng, không có benchmark số lượng tối đa. Nginx giới hạn 512 MiB; tăng upload cần chỉnh proxy tương ứng.

## API

API nghiệp vụ trả `{ success, message, data }`. Endpoint tài liệu nhận query `scope=private|public`, mặc định private (cần quyền nội bộ); client public phải gửi `scope=public`.

| Method | Endpoint | Chức năng |
| --- | --- | --- |
| POST | `/documents/upload` | PDF/DOCX, multipart `files` |
| GET | `/documents/paged` | Danh sách theo kho, `offset`, `limit` |
| GET | `/documents` | Danh sách cũ, giữ tương thích |
| GET | `/documents/upload-limits` | Giới hạn upload |
| DELETE | `/documents/{id}` | Xóa trong kho được chọn |
| GET | `/documents/{id}/file` | Mở/tải bản gốc |
| GET | `/documents/{id}/content` | `offset`, `limit`, `chunk`, `page`, `version`, `digest` |
| GET | `/chat/models` | Lựa chọn model và trạng thái key, không trả key |
| POST | `/chat` | `question`, `model`, `scope` (`private`, `public`, `all`) |
| POST | `/report` | Mẫu `technical`, `meeting`, `research`, hiện dùng nội bộ |
| GET | `/dashboard` | Thống kê theo kho |

```json
{"question":"Điều kiện áp dụng?", "model":"qwen2.5:7b", "scope":"all"}
{"question":"Nội dung tài liệu public?", "model":"openai", "scope":"public"}
```

Chat trả `answer`, `sources`, `model`, `scope`, `coverage`. Đổi mô hình/kho bắt đầu cuộc trao đổi mới. Chat vẫn hỏi từng câu độc lập; chưa tự dùng lịch sử để giải quyết câu nối tiếp. Báo cáo cũ chưa có pipeline truy xuất mở rộng hay độ phủ toàn corpus.

## Kiểm thử và đo độ chính xác

```powershell
cd backend
python tests/run_isolated.py
python -m app.evaluate questions.jsonl --scope private --hybrid-only --output evaluation/hybrid.json
python -m app.evaluate questions.jsonl --scope public --output evaluation/public.json
# Planner + section expansion, do full evidence retrieval with a local model:
python -m app.evaluate questions.jsonl --expanded --model qwen2.5:7b --scope private --output evaluation/expanded.json
cd ../frontend
node --test tests/sources.test.mjs
npm run build
```

Dataset JSONL dùng `expected_documents` hoặc `expected_sources` theo tên/ID tệp và trang/đoạn; nhãn rỗng dành cho câu không có đáp án. Ví dụ:

```json
{"question":"Nội dung mục được hỏi?", "expected_sources":[{"document":"tai-lieu.pdf", "page":3, "chunk_index":4}]}
{"question":"Không có đáp án trong kho", "expected_sources":[]}
```

CLI mặc định đo **baseline retrieval**; `--expanded` đo toàn bộ bằng chứng của pipeline chat, bao gồm planner/mở rộng mục. Cả hai chế độ chưa đánh giá chất lượng câu trả lời. Báo recall, precision nguồn trả về, MRR, abstention, latency và fallback. Cần đánh giá thêm đáp án thực tế với từng mục/bằng chứng chuẩn, gồm câu hỏi diễn đạt lại, nhiều tài liệu, danh sách đầy đủ và đúng vị trí nguồn. Không quy đổi kiểm thử phần mềm thành accuracy. Kiểm thử mới dùng dữ liệu tổng hợp và API mock, chưa đo model/API thật với tài liệu của bạn.

## Sự cố thường gặp

- Upload 400: xem `detail`; PDF scan cần OCR, tệp hỏng/khóa cần xuất lại bản đọc được.
- Không có nguồn sau nâng cấp: kiểm tra đúng kho/đường dẫn và reindex v5; không ingest lại trước khi kiểm tra dữ liệu hiện có.
- OpenAI 403: chỉ chọn kho public. 503: chưa có key; 502: kiểm tra key/quyền model/hạn mức/kết nối.
- Link nguồn 409: chỉ mục/đoạn đã đổi, hỏi lại để có link mới.
- Reranking/planner/reviewer chậm: đo từng bước, giảm ứng viên hoặc tắt từng chức năng để so sánh; có đánh đổi độ chính xác.
- Chat từ chối trả lời do không kiểm chứng được: kiểm tra nguồn, phạm vi ngữ cảnh và khả năng trả JSON của model; không tự hạ kiểm chứng để coi kết luận không được hỗ trợ là đúng.

Cơ chế OpenAI dựa trên [Responses API](https://developers.openai.com/api/reference/python/resources/responses/methods/create) với `store=False`, không tools và không history phía server. Điều này không đồng nghĩa Zero Data Retention. Câu hỏi và bằng chứng public vẫn được gửi qua API khi người dùng chọn OpenAI.

## Rà soát tính ổn định

Truy xuất giữ câu hỏi gốc làm trọng tâm; reviewer kiểm tra trích đoạn nguyên văn cho từng mã nguồn được dẫn. Upload giữ trạng thái khi chuyển trang và có mã chống ingest trùng khi retry; chat/report ngăn gửi lặp, các lỗi thao tác được hiển thị rõ. Thêm `LLM_TIMEOUT=180`, `EMBEDDING_TIMEOUT=120`, `REVIEW_BATCH_SIZE=6`. Không cần reindex nếu đã dùng v5 và không đổi chunking/embedding. Chi tiết, đánh đổi và giới hạn: [PUBLIC_PRIVATE_RAG.md](docs/PUBLIC_PRIVATE_RAG.md).

Kiểm thử frontend: `npm test`, `npm run test:browser` (Edge headless, API giả lập). Chạy `npm run build` lại với cấu hình thật trước khi triển khai; build test dùng API giả riêng.
