# Báo cáo theo dàn ý và bằng chứng từng mục

## Cơ sở lựa chọn phương pháp

Luồng cũ tìm một lần bằng tiêu đề/yêu cầu, lấy số nguồn baseline giới hạn rồi viết toàn bài. Với báo cáo nhiều mục, nguồn phù hợp phần đầu có thể lấn át bằng chứng cho các phần khác. Bản nâng cấp dùng dàn ý và truy xuất độc lập từng mục, giữ nguyên hybrid/RRF, MMR, mở rộng đoạn/mục và kiểm tra nguồn còn tồn tại.

Các tài liệu kỹ thuật đã đối chiếu:

| Nguồn | Điểm tham khảo và cách áp dụng |
| --- | --- |
| [STORM, NAACL 2024](https://arxiv.org/abs/2402.14207) | Nghiên cứu giai đoạn chuẩn bị dàn ý và tìm thông tin trước khi viết. Hệ thống áp dụng ý tưởng dàn ý có trọng tâm từng mục; không triển khai mô phỏng hội thoại nhiều góc nhìn hoặc tìm tài liệu nội bộ trên web. |
| [ALCE, EMNLP 2023](https://arxiv.org/abs/2305.14627) | Tách đánh giá độ trôi chảy, tính đúng và chất lượng trích dẫn. Báo cáo sử dụng reviewer từng mục, đối chiếu quote nguyên văn và kiểm tra số/mã; số mục qua kiểm chứng không phải tỷ lệ accuracy thực tế. |
| [Lost in the Middle, 2023](https://arxiv.org/abs/2307.03172) | Kết quả thực nghiệm cho thấy vị trí bằng chứng trong ngữ cảnh dài có thể ảnh hưởng kết quả ở các mô hình/nhiệm vụ được nghiên cứu. Đây là lý do chọn ngữ cảnh giới hạn theo mục; chưa đo hiệu ứng này trên Qwen/Llama tại máy triển khai. |
| [Microsoft GraphRAG Global Search](https://microsoft.github.io/graphrag/query/global_search/) | Tham khảo phân rã tổng hợp và kiểm soát ngân sách. Chưa dựng knowledge graph/community reports; chọn truy xuất theo mục để tận dụng chỉ mục hiện có và không yêu cầu migration/ingest bổ sung. |

Đây là lựa chọn thiết kế từ nghiên cứu và codebase, không phải triển khai đầy đủ STORM/GraphRAG hay bằng chứng rằng các mức cải thiện trong nghiên cứu cũng đạt trên phần mềm này. Trình duyệt web chỉ được dùng để nghiên cứu công nghệ trong quá trình phát triển; runtime tạo báo cáo không đưa tài liệu nội bộ lên web.

## Luồng xử lý

1. **Kiểm tra quyền và phạm vi.** `/report` yêu cầu quyền nội bộ trước khi xử lý. Báo cáo dùng kho private và mô hình local Qwen/Llama. `model=openai` hoặc `scope=public|all` không được chấp nhận ở API báo cáo; quy tắc OpenAI public của chat giữ nguyên.
2. **Chọn nguồn đầu vào.** Mặc định tìm trong kho nội bộ; có thể chọn 1–20 tài liệu. Tất cả ID phải tồn tại trong metadata private. Điều kiện ID được đưa vào cả dense query Chroma và truy vấn FTS trước giới hạn ứng viên, sau đó kiểm tra lại metadata/tệp và các đoạn mở rộng. Danh sách rỗng không được hiểu là toàn kho.
3. **Chuẩn bị dàn ý.** Người dùng nhập tối đa 4 mục; hoặc model lập dàn ý JSON có heading/focus. Nếu JSON sai, trùng mục hoặc xuất hiện số mới/mã nguồn trong kế hoạch, dùng dàn ý mặc định theo mẫu. Dàn ý là kế hoạch tìm bằng chứng, không phải bằng chứng.
4. **Tìm nguồn cho từng mục.** Truy vấn gồm tiêu đề, heading/focus và tối đa 1.200 ký tự đầu của yêu cầu bổ sung. Model lập dàn ý và model viết vẫn nhận yêu cầu đầy đủ. Không chạy lại query planner/follow-up cho từng mục, giúp giới hạn số lượt suy luận. Reranking chấm tối đa 12 ứng viên mỗi mục theo cấu hình mặc định; vẫn dùng hybrid, MMR và mở rộng bằng chứng.
5. **Viết và kiểm chứng riêng từng mục.** Mỗi mục nhận bằng chứng gốc và mã nguồn ổn định trong toàn báo cáo. Không dùng bản tóm tắt do model tạo thay thế nguồn gốc để xác minh. Reviewer kiểm tra các kết luận với quote từ nguồn, giữ số/mã, phủ định, đơn vị và điều kiện. Nếu vượt đầu ra hoặc không đạt kiểm chứng, mục đó ghi trạng thái thiếu thay vì xuất bản nội dung chưa đạt.
6. **Ghép báo cáo.** Ghép các mục theo dàn ý, thêm thông tin phạm vi và trả `sections`/`coverage`. Khi model/truy xuất gián đoạn, có thể giữ các mục đã hoàn tất, đánh dấu mục còn lại và dừng gọi thêm vào dịch vụ đang lỗi. Lỗi quyền/nguồn ngoài phạm vi vẫn chặn toàn request; nguồn đổi fingerprint giữa các mục trả 409.

Prompt có quy tắc theo từng mẫu: kỹ thuật phân biệt hiện trạng/rủi ro/đề xuất; cuộc họp không biến ý kiến thành quyết định và không tự điền người phụ trách/thời hạn; nghiên cứu không tạo tài liệu tham khảo/DOI hoặc gộp số liệu khác đơn vị, đối tượng, thời kỳ. Khi nguồn khác nhau, yêu cầu trình bày riêng nguồn và điều kiện, không tự kết luận nguồn mới nhất thắng. Chưa có thuật toán chứng minh đầy đủ quan hệ mâu thuẫn hay hiệu lực pháp lý của văn bản.

## Sử dụng và giới hạn

- Chọn mẫu, mô hình, tiêu đề và yêu cầu bổ sung; có thể nhập dàn ý hoặc chọn tài liệu. Danh sách tài liệu có tìm tên tệp và phân trang 50 mục, giữ lựa chọn qua các trang. Tìm tên tệp là tìm chuỗi, không phải tìm ngữ nghĩa nội dung.
- Trong lúc xử lý, form bị khóa để tránh đổi nguồn/mô hình giữa request. Giao diện hiển thị thời gian chờ, không giả lập tiến độ từng bước. Khi request lỗi, giữ yêu cầu để sửa/thử lại; kết quả trước đó có nhãn tiêu đề/mô hình riêng.
- Xem trạng thái từng mục và số tài liệu có bằng chứng. `verified` nghĩa là đã qua các bước kiểm chứng hiện có; không phải xác nhận hoàn toàn đúng bởi chuyên gia. Khi `GROUNDING_VERIFICATION=false`, mục có nội dung được đánh dấu `draft`, số mục đã kiểm chứng là 0.
- `all_documents_reviewed=false` luôn được trả: truy xuất có giới hạn không chứng minh đã đọc toàn bộ corpus. Tài liệu được chọn chưa có bằng chứng sử dụng được báo trong `unrepresented_document_ids`. Yêu cầu bổ sung dài hơn 1.200 ký tự được ghi nhận bằng `search_instructions_truncated`.
- Tối đa 2 nguồn hiển thị cho mỗi tài liệu, ưu tiên nguồn thực sự được dẫn trong các mục đã xuất. Số nguồn hiển thị không phải số đoạn dùng cho generation/reviewer. Mã S1/S2 được giữ bên trong quá trình kiểm chứng, ẩn trên bản xem trước và prose bản xuất; ví dụ mã trong code vẫn giữ nguyên.
- Sao chép/tải Markdown có cấu trúc heading/danh sách, danh mục nguồn cùng origin và vị trí/fingerprint. Parser AST loại đích link do model tạo, HTML và remote images khỏi phần xuất; giữ literal code. Link nguồn nội bộ vẫn yêu cầu đăng nhập, và có thể trả 409 sau khi đổi chỉ mục. Bản Markdown hiển thị nguồn giới hạn như giao diện, chưa có phụ lục toàn bộ bằng chứng/proof hoặc snapshot tài liệu bất biến cho kiểm toán lịch sử.

## Cấu hình

Có mặc định trong code; chỉ bổ sung vào `.env` thực tế nếu cần thay đổi. Compose đã chuyển tiếp các biến này. Không thay embedding/chunking và không cần reindex để nhận nâng cấp báo cáo.

```dotenv
REPORT_CONTEXT_CHARS=10000
REPORT_SECTION_CHUNKS=8
REPORT_RERANK_CANDIDATES=12
REPORT_MAX_SECONDS=420
```

Ngữ cảnh mỗi mục không vượt `min(REPORT_CONTEXT_CHARS, MAX_CONTEXT_CHARS)` và số đoạn được giới hạn bằng `REPORT_SECTION_CHUNKS`. `LLM_NUM_PREDICT` điều khiển đầu ra từng mục. Lớp kiểm chứng dùng `REVIEW_BATCH_SIZE`, `CITATION_REPAIR`, `GROUNDING_VERIFICATION` như chat.

`REPORT_MAX_SECONDS` là ngân sách kiểm tra trước khi bắt đầu mục và trước khi viết, **không phải timeout cứng của toàn request**. Lời gọi đang chạy vẫn chịu `LLM_TIMEOUT`, `RERANK_TIMEOUT`, `EMBEDDING_TIMEOUT`; một mục cũng có thể gồm nhiều lời gọi reviewer/sửa. Khi cần báo cáo dài, nên tách yêu cầu theo phạm vi hoặc nhập ít mục hơn, đo latency thực tế và đồng bộ timeout frontend/proxy. Không chạy song song nhiều mục trên cùng GPU theo mặc định.

API cũ vẫn nhận `template`, `title`, `instructions`; thêm `model`, `document_ids`, `sections` tùy chọn. Response giữ `content`/`sources`, bổ sung trạng thái và coverage. Lịch sử báo cáo vẫn dùng bảng hiện có, không thêm cột hay di chuyển DB. Quyền quản lý đang là khóa nội bộ dùng chung, chưa có tài khoản cá nhân hay hàng đợi báo cáo bền vững.

## Kiểm thử và đánh giá thực tế

Chạy từ thư mục backend:

```powershell
venv\Scripts\python.exe tests/run_isolated.py
```

Runner chạy subprocess với thư mục làm việc/storage tạm, không đọc `.env` thật, xóa cấu hình ứng dụng kế thừa và để key trống. Mọi kiểm thử vẫn cần mock đúng ranh giới suy luận; đây là lớp bảo vệ thêm để khi code được tách service, default storage của test không trỏ nhầm dữ liệu đã ingest.

Bộ test mới kiểm tra nguồn ngoài lựa chọn/scope, lọc trước dense/FTS limit, dàn ý lỗi, mã nguồn xuyên mục, cắt ngân sách, thiếu dữ liệu, model gián đoạn, thay fingerprint, xuất Markdown và luồng DOCX → index thật → report có reviewer qua API. Model/embedding được giả lập; SQLite/Chroma/FTS trong luồng tích hợp là thật và đặt trong thư mục tạm.

Để nghiệm thu với model thật, dùng cùng một bộ tài liệu được phép thử và 3 nhóm báo cáo kỹ thuật/cuộc họp/nghiên cứu. So sánh bản cũ/mới theo các tiêu chí: các mục cần thiết có được bao phủ; mỗi số/mã/điều kiện có đúng nguồn; có bịa quyết định/owner/deadline không; có hòa lẫn các nguồn khác phạm vi không; nguồn mở đúng vị trí; đoạn thiếu có được nói rõ; độ dễ đọc và độ trễ. Thêm trường hợp không có đáp án, số liệu mâu thuẫn, lựa chọn tài liệu ít liên quan và yêu cầu tổng hợp toàn kho. Chưa có số đo accuracy với tài liệu/model thật trong đợt này.

Kết quả kiểm tra ngày 21/10/2026: **146 kiểm thử backend** qua runner cách ly, **18 kiểm thử tiện ích frontend**, **25 kịch bản Edge** đạt; các kịch bản báo cáo được kiểm tra lại sau chỉnh typography. Build production thành công. Edge nối API thật trên DB tạm cũng đạt cho quyền truy cập/phiên và trạng thái model; luồng report có index thật được kiểm tra qua API với model/embedding giả lập. Chưa đo accuracy hay latency với mô hình thật trên tài liệu khách hàng.
