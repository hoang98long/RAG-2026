# Hai kho tài liệu và truy xuất mở rộng

Thay đổi này xử lý các điểm ghi nhận trong `note.docx`: thiếu bằng chứng ở trang khác, thiếu mục trong danh sách, chưa nối được nhiều văn bản, khó truy xuất theo cách diễn đạt đời thường và dẫn nguồn lệch. Chưa có bộ tài liệu/câu hỏi chuẩn đầy đủ để xác nhận tất cả trường hợp thực tế đã được giải quyết.

## Quy tắc dữ liệu

| Mô hình chat | Kho nội bộ | Kho public | Gửi bằng chứng qua OpenAI |
| --- | --- | --- | --- |
| `qwen2.5:7b` mặc định | Có | Có | Không |
| `llama3.1:70b` | Có | Có | Không |
| `openai` (model theo `OPENAI_MODEL`) | Bị chặn | Có | Chỉ bằng chứng public |

Local chọn nội bộ, public hoặc cả hai. OpenAI chỉ chấp nhận `scope=public`; yêu cầu `private` hoặc `all` bị backend trả 403 trước khi mở chỉ mục hay gọi model. Không có fallback từ OpenAI sang kho nội bộ. Không cấu hình key trả 503; lỗi gọi API trả 502 với thông báo không chứa key/prompt.

- Metadata, lịch sử chat, tệp gốc, vector và lexical index nằm riêng theo kho. Dữ liệu hiện có giữ nguyên là nội bộ; không tự copy, đổi nhãn, xóa hay ingest vào public.
- API upload/list/view/delete nhận `scope=private|public` (mặc định private). UUID trùng ở hai kho cũng không làm chúng dùng chung dữ liệu. Không có chức năng tự chuyển tài liệu nội bộ sang public.
- OpenAI được gọi cho lập truy vấn, rerank khi bật reranking, sinh câu trả lời, sửa và kiểm chứng. Mỗi bước có ngữ cảnh chỉ từ kho public. Không đọc lịch sử chat private, không có tool đọc filesystem hoặc truy cập kho nội bộ. Khi đổi mô hình/kho, giao diện bắt đầu cuộc trao đổi mới; hiện chat vẫn xử lý mỗi câu độc lập, không tự gửi lịch sử hội thoại.
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
