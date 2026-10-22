# Hai kho tài liệu và truy xuất mở rộng

Thay đổi này xử lý các điểm ghi nhận trong `note.docx`: thiếu bằng chứng ở trang khác, thiếu mục trong danh sách, chưa nối được nhiều văn bản, khó truy xuất theo cách diễn đạt đời thường và dẫn nguồn lệch. Chưa có bộ tài liệu/câu hỏi chuẩn đầy đủ để xác nhận tất cả trường hợp thực tế đã được giải quyết.

## Chat trực tiếp, không RAG

Trong trang Hỏi đáp, chọn **Chat trực tiếp với OpenAI**. Backend dùng model/key hiện có, không đọc kho public/private, lịch sử DB, vector, Ollama, embedding, planner, reranker hoặc reviewer. Giao diện ẩn danh mục/nguồn; khách chưa đăng nhập vẫn dùng được trong hạn mức public.

- `GET /chat/models?mode=direct`: chỉ kiểm tra key đã cấu hình, không probe Ollama/DB. `GET /chat/models` giữ trạng thái cho RAG.
- `POST /chat/direct`: chỉ nhận `messages` gồm `role=user|assistant` và `content`. Không nhận scope, model tùy ý, system/developer/tool, tools, database URL hay conversation ID. Model lấy từ backend.
- Hội thoại bắt đầu/kết thúc bằng user, luân phiên user/assistant; tối đa 21 tin nhắn, mỗi tin 12.000 ký tự, tổng nội dung UTF-8 tối đa 48.000 byte. Body JSON tối đa 64 KiB kể cả request chunked; dùng chung hạn mức public chat.
- Frontend chỉ gửi các lượt chat trực tiếp thành công, tối đa 10 cặp gần nhất cùng tin nhắn mới; giới hạn thêm kích thước JSON. Bỏ nguyên cặp cũ và thông báo khi lược lịch sử; không tự tóm tắt bằng model.
- Lịch sử chỉ ở bộ nhớ trang, không lưu DB/localStorage. Chuyển chế độ/model/kho, đăng xuất hoặc bắt đầu cuộc trò chuyện mới xóa hội thoại/bản nháp. Nội dung RAG nội bộ không tự gửi sang OpenAI; lỗi API không được dùng làm lịch sử.
- Payload chỉ có system prompt do server kiểm soát và hội thoại người dùng, `store=False`; không tools, previous_response_id, conversation hay file/vector ID. Câu trả lời không qua kiểm chứng bằng chứng RAG.
- Không tự tải ảnh Markdown. Cho mở link web HTTP(S) không có thông tin đăng nhập; chặn protocol thực thi, đường dẫn tương đối và link ứng dụng. RAG vẫn chỉ mở link khớp nguồn.

Ví dụ body:

```json
{"messages":[{"role":"user","content":"Tên tôi là Lan."},{"role":"assistant","content":"Chào Lan."},{"role":"user","content":"Tên tôi là gì?"}]}
```

Thiết kế dựa theo [OpenAI Docs về conversation state](https://developers.openai.com/api/docs/guides/conversation-state). Đây là chat văn bản qua API; chưa có browsing, tệp đính kèm hay các công cụ của web ChatGPT. `store=False` không đồng nghĩa Zero Data Retention. API báo riêng lỗi credit, quota, rate limit, key/quyền model và kết nối; không trả payload lỗi/key từ nhà cung cấp.

## Quy tắc dữ liệu

Phần dưới áp dụng cho chế độ **Hỏi đáp tài liệu (RAG)**.

| Mô hình chat | Kho nội bộ | Kho public | Gửi bằng chứng qua OpenAI |
| --- | --- | --- | --- |
| `qwen2.5:7b` mặc định | Có | Có | Không |
| `llama3.1:70b` | Có | Có | Không |
| `openai` (model theo `OPENAI_MODEL`) | Bị chặn | Có | Chỉ bằng chứng public |

**Chat public dùng được với `qwen2.5:7b` qua Ollama mà không cần đăng nhập nội bộ hay cấu hình OpenAI key.** Đây là mô hình mặc định trên giao diện; khách chưa đăng nhập luôn dùng `scope=public`. Quản trị viên đăng nhập rồi upload vào kho **Public · mô hình local hoặc OpenAI** để cung cấp tài liệu cho luồng này. Không tự chuyển/copy dữ liệu nội bộ sang public.

Trong chế độ RAG, local chọn nội bộ, public hoặc cả hai. OpenAI chỉ chấp nhận `scope=public`; yêu cầu `private` hoặc `all` bị backend trả 403 trước khi mở chỉ mục hay gọi model. Không có fallback từ OpenAI sang kho nội bộ. Không cấu hình key trả 503; lỗi gọi API trả thông báo không chứa key/prompt; phân biệt lỗi credit/quota, rate limit, quyền và kết nối.

- Metadata, lịch sử chat, tệp gốc, vector và lexical index nằm riêng theo kho. Dữ liệu hiện có giữ nguyên là nội bộ; không tự copy, đổi nhãn, xóa hay ingest vào public.
- API upload/list/view/delete nhận `scope=private|public` (mặc định private). UUID trùng ở hai kho cũng không làm chúng dùng chung dữ liệu. Không có chức năng tự chuyển tài liệu nội bộ sang public.
- OpenAI được gọi cho lập truy vấn, rerank khi bật reranking, sinh câu trả lời, sửa và kiểm chứng. Mỗi bước có ngữ cảnh chỉ từ kho public. Không đọc lịch sử chat private, không có tool đọc filesystem hoặc truy cập kho nội bộ. Khi đổi mô hình/kho, giao diện bắt đầu cuộc trao đổi mới; chat RAG xử lý mỗi câu độc lập, không tự gửi lịch sử hội thoại; chat trực tiếp chỉ dùng lịch sử riêng như mô tả phía trên.
- **Embedding ở cả hai kho vẫn chạy qua Ollama**, bằng model embedding hiện có; public có collection và đường dẫn riêng. Điều này cho phép ingest public khi key trống và cho local dùng vector public mà không gọi OpenAI. Phân hệ độc lập về dữ liệu/LLM; truy xuất vector public hiện vẫn cần dịch vụ embedding Ollama. Không phải phân hệ chỉ cần OpenAI và không cần Ollama.
- Key chỉ ở backend; endpoint danh sách mô hình chỉ trả trạng thái đã cấu hình và tên model. Không đưa key vào biến `VITE_*`. Câu hỏi bạn nhập khi chọn OpenAI cũng được gửi tới API; không nhập nội dung bí mật vào chế độ này. Tài liệu đã đánh dấu public được coi là được phép dùng qua API.
- Đây là ranh giới dữ liệu giữa các pipeline, chưa phải cơ chế tài khoản/ACL hay sandbox hệ điều hành riêng. Backend cùng process vẫn có quyền vận hành cả hai kho; nếu cần cách ly process/máy và quyền truy cập của người dùng, cần lớp triển khai/phân quyền tương ứng.

## Cấu hình và nâng cấp dữ liệu

Bổ sung vào `.env` riêng, giữ nguyên đường dẫn private đang triển khai:

```dotenv
PUBLIC_DATABASE_URL=sqlite:///./storage/public/public.db
PUBLIC_CHROMA_DIR=./public_chroma_data
PUBLIC_UPLOAD_DIR=./storage/public/uploads
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4.1-mini
OPENAI_TIMEOUT=90
QUERY_EXPANSION=true
GROUNDING_VERIFICATION=true
EVIDENCE_MAX_CHUNKS=80
EXHAUSTIVE_CONTEXT_CHARS=32000
EXHAUSTIVE_NUM_PREDICT=4096
NEIGHBOR_CHUNKS=1
```

Các đường dẫn tương đối trên dùng khi chạy tại thư mục backend. Settings từ chối DB public trùng DB private và từ chối các thư mục private/public chồng nhau. Chroma public/DB/upload đều được Git/Docker ignore.

Collection chuyển sang **v5** vì nhận diện phụ lục và thêm metadata section chuẩn hóa. Chỉ mục cũ được giữ; không reindex tự động lúc khởi động hoặc khi pull. Dừng API, backup dữ liệu của chính máy triển khai theo [STORAGE_DEPLOYMENT.md](STORAGE_DEPLOYMENT.md), rồi chạy:

```powershell
cd backend
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe -m app.reindex --scope private
# Chỉ chạy nếu kho public đã có dữ liệu và cần chuyển pipeline:
.\venv\Scripts\python.exe -m app.reindex --scope public
ollama pull llama3.1:70b
```

Không cần OpenAI key cho các lệnh ingest/reindex. `--lexical-only --scope ...` chỉ phục hồi lexical từ vector v5 hiện tại, không thay cho reindex v4 → v5. Không copy `.env.example` ghi đè `.env` máy triển khai. Điền `OPENAI_API_KEY` rồi khởi động lại backend khi muốn bật OpenAI. `llama3.1:70b` cần được pull và máy có đủ bộ nhớ; lựa chọn trên giao diện không tự tải model.

Compose giữ volume private hiện có và thêm `public_chroma_data`; DB public/upload public ở nhánh `/app/storage/public` của volume `uploads`. Đặt key trong `.env` gốc của Compose. Tiếp tục dùng cùng project/volume và `docker compose up -d --build`, reindex từng kho bằng `docker compose run --rm backend python -m app.reindex --scope private|public` sau khi dừng process ghi. Không dùng `down -v`.

## Các bước cải thiện retrieval và nguồn

1. Giữ câu hỏi gốc; model tạo tối đa 3 truy vấn diễn đạt lại/tách điều kiện, rồi tối đa 2 truy vấn bổ sung từ đoạn đã tìm được. Có giới hạn vòng truy xuất; planner lỗi giữ câu hỏi gốc. Câu hỏi đời thường không được thay bằng số hiệu/phụ lục tự đoán.
2. Mỗi truy vấn tìm dense + FTS5, hợp nhất RRF rồi rerank. Local dùng Ollama/cross-encoder đã cấu hình; OpenAI dùng public grader khi reranking được bật. Tối đa 3 anchor/tài liệu, tối đa `2 * TOP_K` anchor để một tệp không chiếm hết nguồn.
3. Bổ sung đoạn lân cận. Câu hỏi danh sách/toàn bộ mở rộng mục của anchor, nhận diện “Phụ lục I/01” và đọc các đoạn trong cùng phụ lục ở các trang khác. Tham chiếu phụ lục trong phần quy định cũng được theo tới cùng tài liệu. Truy vấn tiếp theo tìm văn bản/mục bổ sung được nguồn nhắc tới.
4. Bằng chứng cho mô hình không bị chặn ở 2 đoạn/tài liệu. Ngữ cảnh thường dùng `MAX_CONTEXT_CHARS`; câu hỏi danh sách dùng `EXHAUSTIVE_CONTEXT_CHARS`, tối đa `EVIDENCE_MAX_CHUNKS`. Danh mục lớn hơn ngưỡng sẽ bị cắt có thông báo. `coverage.completeness_unverified` cũng bật nếu không xác định được mục nào đã đọc hết. Không coi đây là bằng chứng chắc chắn toàn bộ corpus đã được kiểm tra.
5. Mô hình phải nối điều kiện và danh mục, giữ các mục trong bằng chứng, dẫn đúng mã nội bộ. Reviewer kiểm tra kết luận với đoạn được dẫn; có thể sửa một lần rồi từ chối trả lời nếu vẫn sai/không kiểm chứng được. Mô hình reviewer vẫn có thể mắc lỗi và không thay cho đối chiếu thủ công.
6. Giao diện giữ tối đa **2 nguồn/tài liệu** và ưu tiên những đoạn thực sự được câu trả lời dẫn. Với danh sách dài, đây là các link đại diện, không hiển thị toàn bộ đoạn đã dùng. Mã S tiếp tục ẩn trong phần trả lời. Link có kho, version chỉ mục và hash nội dung; API trả 409 nếu link thuộc chỉ mục cũ hoặc đoạn đã đổi, tránh tô nổi nhầm đoạn. Trang PDF tính theo thứ tự trang của tệp, không theo số trang in trên giấy; DOCX vẫn dùng chỉ số đoạn.

Danh sách dài có ngân sách đầu ra riêng `EXHAUSTIVE_NUM_PREDICT`. Nếu Ollama báo cắt do giới hạn đầu ra hoặc OpenAI trả response chưa hoàn tất, không trình bày phần bị cắt như một câu trả lời đầy đủ. Các ngân sách ký tự không đo chính xác token; có thể cần điều chỉnh sau khi đo với model/tài liệu thật. Planner, reranking và reviewer làm tăng độ trễ/chi phí; tắt riêng `QUERY_EXPANSION` hoặc `GROUNDING_VERIFICATION` để so sánh, có đánh đổi chất lượng.

Vẫn còn giới hạn: PDF scan cần OCR, bảng/hai cột PDF có thể bị trích sai, nhận diện heading dựa regex, mục con có thể tách phạm vi phụ lục, chưa xử lý phiên bản/ngày hiệu lực tự động. Không thể đảm bảo đọc hết danh mục khi parser không trích đúng hoặc tài liệu thiếu. Kiểm thử 64 mục dùng dữ liệu tổng hợp, không chứng minh đáp án đúng cho một thông tư cụ thể.

## API minh họa

```json
{"question":"Liệt kê đầy đủ các trường hợp trong phụ lục đã nêu", "model":"qwen2.5:7b", "scope":"all"}
{"question":"Điều kiện áp dụng trong tài liệu public?", "model":"openai", "scope":"public"}
```

Chat trả thêm `model`, `scope`, `coverage`. `GET /chat/models` trả danh sách model và trạng thái cấu hình OpenAI; key không xuất hiện trong response. URL nguồn giữ `chunk`, `page` và thêm `scope`, `version`, `digest`.

## Kiểm thử và đo lại

```powershell
cd backend
.\venv\Scripts\python.exe -m unittest discover -s tests -v
# Baseline retrieval, đo độc lập theo kho, chưa bao gồm planner/section expansion:
.\venv\Scripts\python.exe -m app.evaluate questions.jsonl --scope private --output evaluation/private.json
.\venv\Scripts\python.exe -m app.evaluate questions.jsonl --scope public --output evaluation/public.json
# Full evidence from multi-query/section expansion; local models only:
.\venv\Scripts\python.exe -m app.evaluate questions.jsonl --expanded --model qwen2.5:7b --scope private --output evaluation/expanded.json
```

Bộ kiểm thử kiểm tra storage/metadata độc lập, chặn OpenAI/private trước retrieval, không có fallback riêng tư, local đọc public/cả hai, payload OpenAI stateless qua mock HTTP, mở rộng phụ lục qua nhiều trang, báo giới hạn ngữ cảnh, sửa kết luận sai dù mã nguồn hợp lệ và phát hiện link nguồn cũ. Không gọi API thật khi key trống.

Để đo phần nâng cấp, cần câu hỏi chuẩn kèm từng mục/bằng chứng mong đợi và kiểm tra nội dung trả lời, không chỉ tên tệp. Với các tình huống trong note, kiểm tra riêng: đủ mục trong phụ lục; điều kiện được nối đúng với danh mục; nhiều tài liệu/phiên bản; câu hỏi diễn đạt lại; trích đúng đoạn. Chưa có số đo accuracy/recall thực tế hay kết quả so sánh `qwen2.5:7b`, `llama3.1:70b`, OpenAI trên dữ liệu của bạn.

Tích hợp dựa theo [OpenAI Responses API](https://developers.openai.com/api/reference/python/resources/responses/methods/create) với `store=False`, không tools/previous_response_id. `store=False` không đồng nghĩa Zero Data Retention và không ngăn nội dung public/câu hỏi được gửi tới OpenAI. Model mặc định có thể đổi trong `OPENAI_MODEL`; tham khảo [GPT-4.1 mini](https://developers.openai.com/api/docs/models/gpt-4.1-mini).

`--expanded` đánh giá toàn bộ bằng chứng chat thực sự đưa cho mô hình, không chỉ 2 link/tài liệu hiển thị; lưu coverage trong JSON. CLI hỗ trợ qwen/llama để đo phần này, không gọi sinh câu trả lời/kiểm chứng. `--hybrid-only` tắt rerank nhưng planner vẫn theo `QUERY_EXPANSION`. Khi so sánh baseline và expanded, chú ý số lượng nguồn trả về khác nhau; không quy đổi recall cao hơn thành accuracy câu trả lời.
## Rà soát độ chính xác và tính ổn định

Bản rà soát tiếp theo giữ collection v5 và đường dẫn dữ liệu, không thay embedding/chunking. Nếu máy đã reindex v5, các thay đổi bên dưới không yêu cầu ingest lại.

- Câu hỏi gốc có trọng số RRF 2; tổng trọng số các truy vấn bổ sung là 1. Rerank đánh giá theo câu hỏi gốc, không ghép nội dung do planner tự sinh thành yêu cầu mới. Chặn truy vấn bổ sung có số/mã phụ lục không xuất hiện trong câu hỏi hoặc đoạn đã tìm được. Đây là quy tắc thận trọng, có thể giảm recall khi cách viết số hiệu khác nhau; cần đo với dữ liệu thực tế.
- Seed cho vòng truy xuất bổ sung lấy từ nhiều tài liệu. Tham chiếu phụ lục được kiểm tra theo bộ kho + tài liệu + phụ lục; mục có trong tệp A không làm mục thiếu ở tệp B được coi là đã đọc. Khi xây prompt, các đoạn trong cùng tệp được đặt theo thứ tự đoạn, vẫn giữ nguyên mã nguồn.
- Reviewer kiểm tra theo lô các nguồn đã được câu trả lời dẫn. Mỗi mã nguồn phải có `claim` khớp một cụm trong câu trả lời và `quote` khớp nguyên văn trong đúng đoạn nguồn; code đối chiếu Unicode NFC và khoảng trắng. Không chấp nhận quote bịa/sai nguồn/thiếu quote dù model báo `supported=true`. Reviewer vẫn chịu trách nhiệm kiểm tra ngữ nghĩa; trùng nguyên văn không tự chứng minh kết luận đúng. Với danh sách dài, kiểm chứng nhiều lô tốn thêm thời gian và có thể từ chối nhiều hơn nếu model không trả đúng schema.
- Thêm `LLM_TIMEOUT=180`, `EMBEDDING_TIMEOUT=120`, `REVIEW_BATCH_SIZE=6`. Đây là timeout/lô theo từng lời gọi, không phải SLA tổng cho toàn bộ câu hỏi hoặc upload. Mô hình chậm có thể cần điều chỉnh sau khi đo. API báo 503/504 khi không kết nối/timeout và không trả payload nhạy cảm của provider.
- Upload giữ hàng chờ và tiến độ trong ứng dụng khi chuyển trang. Mỗi tệp có `Idempotency-Key` UUID; retry cùng mã, cùng kho, cùng tên và cùng SHA-256 trả lại record cũ thay vì embedding lại. Cùng mã nhưng nội dung khác bị 409. Giao diện giữ mã trong bộ nhớ cho các lần thử lại; đóng/reload trình duyệt làm mất hàng chờ/mã. Chọn lại tệp sau đó là upload mới và có thể tạo bản trùng. Khóa chống hai retry đồng thời áp dụng một process, phù hợp giới hạn Chroma hiện tại; không thay cho queue hoặc idempotency nhiều worker.
- Chat/report ngăn submit lặp và hủy chờ request khi rời trang. Hủy chờ trên trình duyệt không bảo đảm dừng tính toán đã bắt đầu ở backend. Request đọc dùng AbortSignal, retry tối đa một lần khi lỗi tạm thời; không retry tự động 400/403/404/409/422. Thao tác ghi không tự retry.
- Reader kiểm tra scope/chỉ số/hash của link, giữ kiểm tra hash khi quay về trang chứa nguồn, không hiển thị dữ liệu cũ khi refetch lỗi. Xóa tài liệu có hộp xác nhận trong ứng dụng, khóa lựa chọn kho trong khi chờ và hiển thị lỗi có thể thử lại. Dashboard phân biệt lỗi tải với số đếm 0. Lỗi clipboard được xử lý; có ranh giới lỗi trang và chia bundle theo trang.

## Kiểm thử giao diện

Tại frontend:

```powershell
npm ci
npm test
npm run test:browser
# Build sử dụng cấu hình thật trước khi triển khai:
npm run build
```

Playwright chạy Edge headless sẵn có trên máy; có thể chọn `PLAYWRIGHT_CHANNEL=chrome` hoặc cài browser/channel phù hợp khi dùng môi trường khác. Bộ chạy tạo build cho kiểm thử với API giả tại `127.0.0.1:59998`, preview tại `127.0.0.1:4179`, và chỉ dừng đúng child process nó tạo. Không gọi backend thật hoặc đọc tài liệu đã ingest. Kết quả/screenshot nằm ở `frontend/test-results/`, được ignore. Không triển khai build API giả từ lượt kiểm thử: chạy lại `npm run build` hoặc build Docker bằng cấu hình thật.

Kiểm thử cover lựa chọn mặc định, OpenAI/public và xóa draft khi đổi model, tránh submit lặp, link public mở đúng chunk, lỗi xóa tài liệu, nguồn cũ 409 không retry, kiểm tra lại hash sau phân trang, upload khi chuyển trang/retry, context thiếu `crypto.randomUUID`, tệp không hỗ trợ, link sai scope và clipboard bị từ chối. Kiểm tra mobile xác nhận chat cuộn bên trong và không tràn ngang khi tên nguồn rất dài. Các lượt chạy dùng API giả, không chứng minh hiệu năng/accuracy của model thật.

Dependency được cập nhật các bản vá trong khoảng phiên bản hiện tại. `npm audit --omit=dev` đã không còn cảnh báo tại lúc kiểm tra; audit đầy đủ vẫn có 7 cảnh báo thuộc chuỗi công cụ build Tailwind 3. Công cụ đề xuất chuyển major Tailwind 4, chưa thực hiện chuyển đổi CSS trong lượt sửa này. Chỉ dùng dev/preview server cho phát triển; production phục vụ build tĩnh. Báo cáo audit phụ thuộc thời điểm và cần kiểm tra lại khi triển khai.

Tham khảo triển khai: [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs), [TanStack Query cancellation](https://tanstack.com/query/latest/docs/framework/react/guides/query-cancellation), [Playwright](https://playwright.dev/docs/test-webserver).

Nội dung Markdown trong chat/báo cáo không tự tải ảnh từ URL do model sinh; hiển thị mô tả thay thế để tránh request ngoài ý muốn và ảnh lỗi. Liên kết vẫn mở khi người dùng bấm. Lỗi dịch vụ kiểm chứng được phân biệt với việc thiếu bằng chứng trong câu trả lời.

## Kiểm tra nguồn còn khả dụng và phạm vi bằng chứng

Đợt rà soát này giữ nguyên định dạng collection v5, embedding, schema và đường dẫn dữ liệu. Máy đã ingest v5 không cần ingest lại chỉ để nhận các thay đổi này.

- Chat và báo cáo kiểm tra các tài liệu ứng viên với DB metadata của đúng kho trước khi đưa nội dung vào planner, rerank hoặc sinh câu trả lời. Chỉ dùng đoạn có record còn tồn tại, tên tệp khớp và tệp gốc còn nằm trong thư mục upload của kho đó. Đoạn còn sót sau upload lỗi, tệp bị mất hoặc đường dẫn trỏ sang kho khác bị loại khỏi lần truy xuất. Kiểm tra theo các ID ứng viên, mỗi truy vấn SQL tối đa 256 ID; không tải cả danh mục tài liệu. Kiểm tra lại khi mở rộng đoạn/mục để xử lý tài liệu bị xóa giữa chừng.
- OpenAI chỉ mở metadata public trong bước kiểm tra nguồn. Local chọn cả hai kho kiểm tra riêng từng DB. Lịch sử vẫn được lưu theo quy tắc phân kho hiện có. Việc lọc không tự xóa chỉ mục hoặc sửa dữ liệu; nếu mất tệp gốc cần khôi phục đúng kho hoặc ingest lại có chủ đích. Không kiểm tra lại SHA-256 của toàn bộ tệp ở mỗi câu hỏi; thay tệp trực tiếp trên ổ đĩa vẫn cần reindex để đồng bộ nội dung.
- Sau các đoạn truy xuất chính, ngữ cảnh ưu tiên phụ lục được hỏi, rồi phụ lục được nguồn tham chiếu, trước khi mở rộng các mục chung. `coverage.section_retained` đếm số đoạn thực sự được đưa vào prompt theo từng mục. Phụ lục không tìm thấy hoặc chỉ giữ được một phần làm `completeness_unverified=true`, kể cả câu hỏi không chứa từ “toàn bộ”. `incomplete_referenced_sections` phân biệt thiếu trong ngữ cảnh với `missing_referenced_sections` là chưa tìm thấy mục.
- Reviewer yêu cầu bằng chứng cho từng dòng có trích dẫn, theo từng mã nguồn trên dòng đó. Một claim chỉ xuất hiện ở dòng khác không thể xác nhận dòng đang dẫn sai nguồn. Model được hướng dẫn đặt trích dẫn cùng dòng với kết luận. Đối chiếu nguyên văn vẫn chỉ là lớp kiểm tra bổ sung; đánh giá quan hệ ngữ nghĩa phụ thuộc reviewer và có thể sai hoặc từ chối câu đúng.
- CLI `app.evaluate` cũng áp dụng kiểm tra metadata/tệp nguồn, cho cả baseline và `--expanded`; báo cáo ghi `configuration.catalogue_validated=true`. Nhờ đó phép đo không tính các đoạn vector không còn mở được qua ứng dụng là bằng chứng hợp lệ. CLI vẫn chỉ đo retrieval, không đo chất lượng câu trả lời cuối cùng.
- Giao diện trừ chiều cao thực tế của thanh upload nền khi bố trí chat/reader, tránh đẩy ô nhập chat ra ngoài màn hình desktop. Khi chat lỗi, câu hỏi được khôi phục nếu ô nhập còn trống; không ghi đè bản nháp mới người dùng đang soạn. Không tự gửi lại request chat.

Kiểm thử sau thay đổi: 84 kiểm thử backend, 11 kiểm thử tiện ích frontend, 14 kịch bản trên Edge và build production đạt. Các kiểm thử mới dùng SQLite tạm và mô hình/API giả; kiểm tra nguồn mồ côi, tệp mất/sai kho, tài liệu bị xóa giữa chừng, truy vấn SQL có giới hạn, phụ lục bị chen khỏi ngữ cảnh, claim dẫn nhầm dòng, giữ bản nháp khi lỗi và chat trong lúc upload nền. Đây không phải số đo accuracy trên tài liệu thật hoặc cam kết không còn lỗi.

## Đa dạng ứng viên và phân bổ ngữ cảnh

Rerank bổ sung MMR theo thứ hạng với `RERANK_DIVERSITY_LAMBDA=0.75`: giữ một phần tư ứng viên đầu, chọn thêm trong cửa sổ tối đa bốn lần `RERANK_CANDIDATES` để các đoạn gần trùng ít chiếm hết lượt chấm. Tên tệp không tham gia độ giống; code dùng bigram văn bản nguồn, không gọi thêm embedding hoặc LLM. Giá trị 1 giữ cách chọn top pool cũ. Rerank tắt thì MMR không chạy.

Trong từng nhóm nội dung mở rộng cùng mức ưu tiên, lấy luân phiên theo kho/tài liệu/mục để một phụ lục dài không chiếm toàn bộ ngữ cảnh trước phụ lục khác. Vẫn ưu tiên anchor và phụ lục được hỏi, giữ giới hạn ký tự/số đoạn và cảnh báo thiếu. Không gộp các điều khoản gần giống có thể khác số liệu hoặc phủ định.

CLI thêm `--no-diversity` để so sánh với thứ tự cũ; báo cáo thêm `complete_evidence_rate` là tỷ lệ câu tìm đủ tất cả bằng chứng được gán nhãn. Metric không kiểm tra nội dung câu trả lời hoặc chứng minh đã tìm hết corpus. Cấu hình, công thức, nguồn nghiên cứu, cách đo và đánh đổi được ghi tại [RAG_ACCURACY.md](RAG_ACCURACY.md#rà-soát-thuật-toán-mmr-và-phân-bổ-ngữ-cảnh).

Collection vẫn là v5; nhận nâng cấp không cần ingest lại nếu đã dùng v5. Chưa có benchmark với model thật trên tài liệu của người dùng, nên mặc định 0.75 cần được đánh giá/hiệu chỉnh thay vì coi là giá trị tối ưu.

## Truy cập từ bên ngoài: quyền public và quyền nội bộ

Ứng dụng có hai mức truy cập. Người chưa đăng nhập chỉ xem/hỏi kho public. Quyền nội bộ mở thêm private/all và quản lý tài liệu. Khóa truy cập nội bộ độc lập với `OPENAI_API_KEY`; không đưa bất kỳ khóa nào vào biến `VITE_*` hoặc mã frontend.

| Chức năng | Chưa đăng nhập | Có quyền nội bộ |
| --- | --- | --- |
| Chat `scope=public`, đọc/danh mục/thống kê public | Cho phép | Cho phép |
| Chat `scope=private/all`, đọc/danh mục/thống kê private | 401 | Cho phép |
| Upload hoặc xóa tài liệu ở cả hai kho | 401 | Cho phép |
| Tạo báo cáo từ private | 401 | Cho phép |
| OpenAI với `scope=private/all` | Không cho phép | Vẫn không cho phép |

### Cấu hình và đăng nhập

Trên từng máy triển khai, thêm vào **`.env` thật** (giữ nguyên các đường dẫn DB/index/upload đã có):

```dotenv
INTERNAL_ACCESS_TOKEN=<khóa ngẫu nhiên từ 32 đến 512 ký tự>
SESSION_MAX_AGE=14400
SESSION_COOKIE_SECURE=true
CORS_ORIGINS=https://ten-mien-cua-ban.example
PUBLIC_CHAT_RATE_LIMIT=20
PUBLIC_CHAT_MAX_CONCURRENT=2
```

Tạo khóa trên máy quản trị bằng `python -c "import secrets; print(secrets.token_urlsafe(32))"`, lưu riêng và nhập tại nút **Đăng nhập nội bộ**. Không commit khóa. Các `.env.example` để `INTERNAL_ACCESS_TOKEN=` trống; khi chưa cấu hình, private và các thao tác quản lý bị khóa, không tự mở quyền cho localhost hoặc mạng LAN. Khóa cần ngẫu nhiên, không chỉ một chuỗi lặp đủ độ dài.

`SESSION_COOKIE_SECURE=false` chỉ dành cho phát triển qua HTTP trên máy tin cậy; HTTPS ở production đặt `true`. Giao diện mặc định gọi `/api`, Vite proxy cho phát triển và Nginx proxy cho Docker. Cách này giữ API cùng origin với giao diện, tránh phụ thuộc cookie giữa hai site. Khi chạy Docker, cấu hình tại `.env` gốc cho Compose; khi chạy backend trực tiếp, dùng `backend/.env`. Không sửa `.env.example` để cung cấp khóa thật.

### Cách kiểm soát quyền

- Backend kiểm tra quyền trên API, không dựa vào option bị ẩn trên giao diện. Các API ghi được chặn ở middleware trước khi FastAPI đọc/spool multipart. JSON chat/report tối đa 64 KiB, JSON auth tối đa 16 KiB; upload giữ giới hạn dung lượng riêng.
- `/auth/login` nhận khóa qua HTTPS và cấp session ngẫu nhiên qua cookie `HttpOnly`, `SameSite=Lax`. Khóa gốc không được lưu trong localStorage/sessionStorage hoặc trả về response. Server chỉ giữ hash session và thời hạn trong bộ nhớ, tối đa 256 phiên. `/auth/logout` thu hồi phiên ở server; cookie cũ không dùng lại được. Đổi khóa hoặc khởi động lại process làm hết hiệu lực phiên cũ.
- Thao tác ghi dùng cookie phải có `Origin` của ứng dụng hoặc một origin được cấu hình rõ trong `CORS_ORIGINS`; wildcard `*` bị từ chối. Client quản trị gọi trực tiếp API có thể dùng `Authorization: Bearer <INTERNAL_ACCESS_TOKEN>`; không truyền khóa trên URL. Header Bearer sai không được rơi về cookie đúng.
- Chat public không khởi tạo session metadata private, kể cả khi dùng model local. Scope được kiểm tra lại ở ứng viên, đoạn mở rộng, bằng chứng cuối cùng và nguồn trả về. Câu hỏi hay nội dung tài liệu không thể thay đổi scope thực thi. Các tham số ngoài schema như `history`, `tools`, `database_url`, `system_prompt` bị từ chối.
- Giao diện chỉ mở link Markdown do model sinh nếu khớp chính xác một nguồn của câu trả lời và cùng origin. Nguồn/danh mục/nội dung trả về sai kho bị chặn trước khi hiển thị. Đăng xuất xóa hội thoại, bản nháp, hàng chờ và cache ứng dụng; các tab khác nhận thông báo đăng xuất. Quyền hết hạn vẫn được backend kiểm tra ở từng request.
- API trả `Cache-Control: no-store`; Nginx có CSP, chống nhúng iframe và `nosniff`. Public chat chưa đăng nhập mặc định giới hạn 20 yêu cầu/phút/IP, tối đa 2 câu đang xử lý trong một process, trả 429 khi vượt. Đây không phải hạn mức tài khoản hay cơ chế chống DoS phân tán.

### Docker và reverse proxy

Compose chỉ mở cổng frontend `3000` ra các interface. Backend `8000`, Ollama `11434`, Chroma cũ `8001` bind `127.0.0.1`; Docker network vẫn cho các service cần thiết liên lạc. Không mở trực tiếp các cổng dữ liệu/model ra Internet. Backend thực tế dùng Chroma nhúng; service Chroma cũ chuyển sang profile `legacy-chroma`, không cần chạy mặc định hoặc cho ghi song song cùng volume.

Máy đã chạy Compose cũ cần dừng service Chroma cũ bằng `docker compose stop chroma`, rồi cập nhật/recreate các service. Giữ nguyên project name và volumes; không dùng `down -v`, không copy DB từ máy khác. Các thay đổi này không yêu cầu ingest lại v5.

Đặt HTTPS reverse proxy phía trước frontend và cấu hình `CORS_ORIGINS` đúng origin bên ngoài. Proxy `/api` chỉ chuyển tới backend cố định; Nginx ghi lại `X-Forwarded-For` từ địa chỉ kết nối thay vì tin header do client gửi. `TRUSTED_PROXY_IPS` trong Compose mặc định `*` để Uvicorn nhận proxy của Docker, chỉ phù hợp khi backend được cô lập như cấu hình loopback/network hiện tại. Nếu tự mở backend hoặc đổi topology, giới hạn danh sách proxy được tin cậy. Với thêm một TLS ingress, cấu hình real IP theo đúng IP proxy tin cậy nếu cần hạn mức từng người dùng; mặc định nhiều người qua cùng proxy/NAT có thể dùng chung hạn mức.

Mô hình quyền hiện tại là **public và một khóa quản trị nội bộ dùng chung**, chưa có tài khoản cá nhân, phân quyền từng tài liệu/nhóm, nhật ký danh tính hay SSO. Session và hạn mức ở bộ nhớ phù hợp một process hiện tại; mở rộng nhiều worker cần session/rate-limit store chung và xem lại Chroma. Người đã được phép đọc vẫn có thể tải/lưu nội dung, nên đăng xuất không thu hồi bản đã tải xuống.

Cách thiết kế dựa trên nguyên tắc kiểm tra từng request và từ chối mặc định của [OWASP Authorization](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html), kết hợp [kiểm tra Origin và SameSite để chống CSRF](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html). Đây không phải chứng nhận bảo mật hoặc thay thế đánh giá triển khai thực tế.

### Giao diện và kiểm chứng câu trả lời

Bố cục mới thống nhất sidebar, thanh điều hướng/quyền truy cập, khoảng cách và hệ màu. Dashboard có thống kê cùng lối vào chức năng chính; chat giữ vùng cuộn riêng, reader giữ viewport và thanh upload nền được tính vào chiều cao. Người public chỉ thấy scope public và không có thao tác quản lý.

Tiếp tục dùng hybrid/RRF, MMR và mở rộng mục/phụ lục. Lớp đối chiếu quote bổ sung kiểm tra số/mã trong claim phải có trong quote nguyên văn; ví dụ claim `48 tháng` không được xác nhận bằng quote `24 tháng`, kể cả reviewer báo supported. Đây là kiểm tra cho cụm claim trực tiếp, chưa chứng minh toàn bộ ngữ nghĩa hay tính toán suy ra. Giữ nguyên định dạng số từ nguồn giúp tránh từ chối do thay cách viết. Chưa có benchmark accuracy với model thật trên tài liệu của người dùng.

Tại frontend có thêm `npm run test:access`: build `/api`, chạy Edge với API thật trên loopback và hai SQLite/upload tạm, kiểm tra public/private, cookie HttpOnly, đăng nhập/đăng xuất và thu hồi cookie. Không gọi Ollama/OpenAI hoặc đọc DB đã ingest. Cần Python trong `backend/venv`; có thể chỉ định `RAG_TEST_PYTHON`. Bộ test workflow vẫn dùng API giả. Khi triển khai, chạy build theo cấu hình thật và kiểm tra Nginx/TLS tại máy triển khai.

Báo cáo cũng sử dụng `GROUNDING_VERIFICATION` trước khi xuất nội dung, thay cho chỉ kiểm tra mã trích dẫn như trước. Báo cáo hiện đã chuyển sang truy xuất và kiểm chứng theo từng mục; xem REPORT_RAG.md. Truy xuất có giới hạn không chứng minh đã đọc toàn corpus; kiểm chứng có thể tăng độ trễ hoặc từ chối khi không đủ bằng chứng.

Đợt rà soát này đã kiểm tra giao diện desktop/mobile, trạng thái upload, các ca public/private và luồng đăng nhập thật bằng Edge với API/DB tạm. Các file DB/tài liệu đã ingest không bị thay thế; khóa trong các tệp mẫu để trống. Kiểm thử cookie qua API thật không thay thế việc kiểm tra Nginx, TLS và firewall của máy triển khai.

Kết quả kiểm tra cập nhật ngày 20/10/2026: **131 kiểm thử backend, 14 kiểm thử tiện ích frontend, 22 kịch bản Edge** đạt; build production thành công. Luồng truy cập bằng Edge với API thật và DB tạm cũng đạt. Compose kiểm tra cấu hình/port; chưa chạy triển khai Nginx/TLS trên máy production. Không có số đo accuracy với Ollama/OpenAI thật trong lượt này.

## Kiểm tra vận hành trước thử nghiệm khách hàng

Quy trình cấu hình, backup, healthcheck, thử upload/chat/nguồn, nghiệm thu ranh giới public/private và rollback: [PILOT_DEPLOYMENT.md](PILOT_DEPLOYMENT.md). API `/ready` và `/chat/models` chỉ probe inventory Ollama có giới hạn/cache, không mở private DB hoặc gửi tài liệu tới bên ngoài. `app.preflight` là công cụ CLI chỉ đọc chạy bởi người vận hành; không mở thành API public và không tự ingest/reindex.

Giao diện chặn gửi khi model/embedding chưa sẵn sàng, giữ câu hỏi để thử lại, có phục hồi khi không kiểm tra được phiên truy cập. Bộ kiểm thử bổ sung có luồng DOCX → SQLite/Chroma/FTS → RAG có reviewer → nguồn có fingerprint → xóa theo kho, với model/embedding giả lập và dữ liệu tạm. Đây không phải benchmark accuracy hoặc tải trên máy khách hàng.


## Báo cáo theo dàn ý (21/10/2026)

Chức năng báo cáo được nâng cấp thành lập dàn ý → tìm bằng chứng từng mục → viết/kiểm chứng → ghép báo cáo có coverage. Có thể chọn tài liệu nội bộ, model local và dàn ý; bộ lọc áp dụng trước giới hạn dense/FTS rồi kiểm tra lại ở source catalogue và bằng chứng cuối. `/report` vẫn yêu cầu quyền nội bộ, không thêm đường cho OpenAI đọc private. Xem [REPORT_RAG.md](REPORT_RAG.md) để biết nguồn nghiên cứu, cấu hình, ý nghĩa trạng thái, cách xuất và các giới hạn.

Backend có runner kiểm thử cách ly `python tests/run_isolated.py`, dùng subprocess với default storage/CWD tạm và không đọc `.env` thật. Model/embedding trong các bài kiểm thử báo cáo đều được giả lập; không dùng số mục đã kiểm chứng hay số test đạt để suy ra accuracy trên model/tài liệu thật.
