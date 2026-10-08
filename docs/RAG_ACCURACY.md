# Nghiên cứu cải thiện độ chính xác RAG

## Chẩn đoán pipeline trước thay đổi

Pipeline đã có chunking theo trang, embedding đa ngôn ngữ, BM25/RRF và liên kết trích dẫn. Tuy nhiên, RRF chỉ hợp nhất thứ hạng, không đánh giá đoạn có trả lời được câu hỏi hay không; ngưỡng cosine chỉ áp dụng nhánh vector. BM25 vẫn có thể chọn đoạn có từ chung nhưng không chứa bằng chứng. Công cụ đánh giá cũ chỉ kiểm tra tên tài liệu, nên tìm đúng tệp/sai trang vẫn được tính đúng.

Chunk đơn lẻ còn có thể thiếu chủ thể/phạm vi. DOCX trích văn bản thuần làm quan hệ hàng/cột khó đọc. Prompt yêu cầu trích dẫn nhưng trước đây không có kiểm tra mã nguồn sau generation.

## Cơ sở nghiên cứu và phạm vi áp dụng

1. [Anthropic: Contextual Retrieval](https://www.anthropic.com/engineering/contextual-retrieval) nghiên cứu bổ sung ngữ cảnh cho chunk trước embedding và BM25, sau đó rerank ứng viên. Dự án áp dụng phần ngữ cảnh **xác định từ nguồn**: tên tệp, tiêu đề mục/cột. Không sinh giải thích bằng LLM khi ingestion để tránh thêm dữ kiện và chi phí chưa được đo. Đây là một biến thể metadata context, không tương đương phương pháp hay kết quả benchmark của bài viết.
2. [Qwen3 Embedding](https://github.com/QwenLM/Qwen3-Embedding) hỗ trợ instruction cho retrieval. Tiếp tục dùng tiền tố instruction trên query của Qwen3 và giữ model embedding riêng với model generation. Tăng kích thước embedding là thử nghiệm cần reindex/benchmark, không phải mặc định đảm bảo tốt hơn.
3. [BGE reranker v2 m3](https://huggingface.co/BAAI/bge-reranker-v2-m3) là reranker đa ngôn ngữ chấm cặp query/passage. Thêm adapter CrossEncoder tùy chọn. Score phụ thuộc model/activation, cần calibrate ngưỡng riêng; không dùng thang grade của Ollama cho BGE.

Không dùng phần trăm cải thiện từ nguồn nghiên cứu để dự đoán kết quả trên corpus tiếng Việt của dự án.

## Quyết định kiến trúc đã triển khai

- Giữ FastAPI/SQLite/Chroma/Ollama để không tăng vận hành trước khi có bằng chứng cần hạ tầng khác.
- Chuyển thành truy xuất hai tầng: dense + lexical → RRF → rerank → chọn nguồn có giới hạn.
- Ollama grader mặc định dùng cùng model generation, chấm grade 0–3 bằng JSON schema, kiểm tra mã ứng viên đầy đủ/duy nhất, sắp xếp ổn định theo grade rồi RRF. Đây là LLM grader, không phải reranker chuyên dụng và có thể chấm sai.
- Lọc grade 0/1; chấp nhận grade 2/3. Đây là điểm khởi đầu để đo, không phải ngưỡng xác suất đã calibrate. Khi grader lỗi, dùng hybrid fallback và đánh dấu trong nguồn/log.
- Cross-encoder là lựa chọn đánh đổi thêm dependency/bộ nhớ để thử chuyên môn hóa reranking. Chưa tải/cài model này hoặc kiểm chứng inference thật trong môi trường hiện tại.
- Ngữ cảnh tìm kiếm được bổ sung từ cấu trúc nguồn, giữ riêng văn bản dẫn chứng. Không phá liên kết trang/chunk hoặc giới hạn 2 nguồn/tài liệu.
- PDF giữ phạm vi mục giữa các trang, DOCX chia khối theo heading và hàng bảng; lưu chỉ mục v4 riêng để không trộn vector cũ.
- Generation kiểm tra sự tồn tại/tính hợp lệ của mã trích dẫn và sửa một lần. Không gọi đây là kiểm chứng nội dung hoặc bộ phát hiện hallucination.

## Cách xác định thay đổi nào có ích

Dùng cùng dataset được gán nhãn ở mức trang/đoạn, gồm cả câu không có đáp án. So sánh `--hybrid-only` với reranking; tiếp đó mới thay model/size/chunking. Ghi recall, precision, MRR, độ trễ và fallback. Một thay đổi giảm recall có thể làm câu trả lời thiếu điều kiện dù precision tăng.

Kiểm tra thủ công câu trả lời: số liệu/đơn vị, chủ thể, phủ định, điều kiện áp dụng, ngày hiệu lực, mâu thuẫn và nguồn hỗ trợ từng kết luận. Chọn tham số trên tập phát triển, đo kết quả cuối trên tập kiểm tra độc lập. Tạo câu từ tài liệu bằng cùng LLM chỉ phù hợp tạo dữ liệu nháp, cần người kiểm tra; không dùng làm bằng chứng chất lượng thực tế một mình.

## Hướng chưa triển khai

- OCR/parser giữ bố cục PDF: ưu tiên khi corpus là scan, bảng, hai cột. Đổi retrieval không phục hồi dữ liệu chưa trích được.
- Parent-child/neighbor retrieval: ưu tiên khi tìm đúng đoạn nhưng thiếu điều kiện nằm bên cạnh; cần giữ provenance cho từng phần và thỏa yêu cầu giới hạn nguồn.
- Query rewriting theo lịch sử: ưu tiên cho câu nối tiếp, phải tránh thay đổi tên/mã/ngày trong câu gốc.
- Metadata phiên bản/ngày hiệu lực và lọc tài liệu: ưu tiên cho corpus quy định nhiều phiên bản; ngày không có trong nguồn không được tự gán.
- Truy xuất riêng theo từng mục báo cáo và kiểm tra độ phủ: ưu tiên cho báo cáo toàn corpus.
- PostgreSQL/keyword search dịch vụ riêng: chỉ chuyển khi đa worker/corpus lớn đòi cache nhất quán và tránh tải toàn văn vào RAM.

Các hướng này chưa được coi là đã hoàn thành chỉ vì đã nêu trong tài liệu.

## Mở rộng corpus: thay đổi triển khai v4

Lexical index đã chuyển sang SQLite FTS5 trên đĩa, không giữ full corpus trong RAM khi query. Streaming extraction/embedding batch và reader phân trang giảm tải cho một tệp lớn. Phạm vi dense/lexical tăng lên 48 mỗi nhánh, rerank 32, giữ giới hạn nguồn và ngân sách prompt.

Không coi corpus lớn hơn đồng nghĩa chất lượng giữ nguyên: FTS5 thay thuật toán/điểm BM25, phân đoạn DOCX theo cửa sổ có thể đổi ranh giới, nguồn liên quan cạnh tranh với nhiều ứng viên hơn. Cần reindex v4, rà nhãn chunk, so sánh lại các câu hỏi đúng trang/đoạn và câu không có đáp án. Chưa triển khai hàng đợi công việc bền vững, nhiều worker ghi hoặc dịch vụ vector phân tán.
