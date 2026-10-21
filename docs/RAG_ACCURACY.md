# Nghiên cứu cải thiện độ chính xác RAG

## Chẩn đoán pipeline trước thay đổi

Pipeline đã có chunking theo trang, embedding đa ngôn ngữ, BM25/RRF và liên kết trích dẫn. Tuy nhiên, RRF chỉ hợp nhất thứ hạng, không đánh giá đoạn có trả lời được câu hỏi hay không; ngưỡng cosine chỉ áp dụng nhánh vector. BM25 vẫn có thể chọn đoạn có từ chung nhưng không chứa bằng chứng. Công cụ đánh giá cũ chỉ kiểm tra tên tài liệu, nên tìm đúng tệp/sai trang vẫn được tính đúng.

Chunk đơn lẻ còn có thể thiếu chủ thể/phạm vi. DOCX trích văn bản thuần làm quan hệ hàng/cột khó đọc. Prompt yêu cầu trích dẫn nhưng trước đây không có kiểm tra mã nguồn sau generation.

## Cơ sở nghiên cứu và phạm vi áp dụng

1. [Anthropic: Contextual Retrieval](https://www.anthropic.com/engineering/contextual-retrieval) nghiên cứu bổ sung ngữ cảnh cho chunk trước embedding và BM25, sau đó rerank ứng viên. Dự án áp dụng phần ngữ cảnh **xác định từ nguồn**: tên tệp, tiêu đề mục/cột. Không sinh giải thích bằng LLM khi ingestion để tránh thêm dữ kiện và chi phí chưa được đo. Đây là một biến thể metadata context, không tương đương phương pháp hay kết quả benchmark của bài viết.
2. [Qwen3 Embedding](https://github.com/QwenLM/Qwen3-Embedding) hỗ trợ instruction cho retrieval. Tiếp tục dùng tiền tố instruction trên query của Qwen3 và giữ model embedding riêng với model generation. Tăng kích thước embedding là thử nghiệm cần reindex/benchmark, không phải mặc định đảm bảo tốt hơn.
3. [BGE reranker v2 m3](https://huggingface.co/BAAI/bge-reranker-v2-m3) là reranker đa ngôn ngữ chấm cặp query/passage. Thêm adapter CrossEncoder tùy chọn. Score phụ thuộc model/activation, cần calibrate ngưỡng riêng; không dùng thang grade của Ollama cho BGE.

Không dùng phần trăm cải thiện từ nguồn nghiên cứu để dự đoán kết quả trên corpus tiếng Việt của dự án.

## Quyết định kiến trúc ban đầu (v4)

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

## Các hướng đề xuất ở phiên bản đầu

- OCR/parser giữ bố cục PDF: ưu tiên khi corpus là scan, bảng, hai cột. Đổi retrieval không phục hồi dữ liệu chưa trích được.
- Parent-child/neighbor retrieval: v5 đã bổ sung đoạn lân cận và mở rộng mục/phụ lục; tiếp tục kiểm tra provenance và độ phủ khi tài liệu có cấu trúc phức tạp.
- Query rewriting theo lịch sử: ưu tiên cho câu nối tiếp, phải tránh thay đổi tên/mã/ngày trong câu gốc.
- Metadata phiên bản/ngày hiệu lực và lọc tài liệu: ưu tiên cho corpus quy định nhiều phiên bản; ngày không có trong nguồn không được tự gán.
- Truy xuất riêng theo từng mục báo cáo và kiểm tra độ phủ: ưu tiên cho báo cáo toàn corpus.
- PostgreSQL/keyword search dịch vụ riêng: chỉ chuyển khi đa worker/corpus lớn đòi cache nhất quán và tránh tải toàn văn vào RAM.

Các hướng ngoài phần v5/cập nhật bên dưới vẫn chưa được coi là đã hoàn thành chỉ vì đã nêu trong tài liệu.

## Mở rộng corpus: thay đổi triển khai v4

Lexical index đã chuyển sang SQLite FTS5 trên đĩa, không giữ full corpus trong RAM khi query. Streaming extraction/embedding batch và reader phân trang giảm tải cho một tệp lớn. Phạm vi dense/lexical tăng lên 48 mỗi nhánh, rerank 32, giữ giới hạn nguồn và ngân sách prompt.

Không coi corpus lớn hơn đồng nghĩa chất lượng giữ nguyên: FTS5 thay thuật toán/điểm BM25, phân đoạn DOCX theo cửa sổ có thể đổi ranh giới, nguồn liên quan cạnh tranh với nhiều ứng viên hơn. Cần reindex v4, rà nhãn chunk, so sánh lại các câu hỏi đúng trang/đoạn và câu không có đáp án. Chưa triển khai hàng đợi công việc bền vững, nhiều worker ghi hoặc dịch vụ vector phân tán.

## Pipeline v5

Hai kho private/public và truy xuất mở rộng được mô tả tại [PUBLIC_PRIVATE_RAG.md](PUBLIC_PRIVATE_RAG.md). Các giới hạn 2 đoạn/tài liệu trong phần nghiên cứu trước áp dụng baseline/báo cáo; chat v5 tách bằng chứng để trả lời khỏi link nguồn hiển thị.

## Rà soát thuật toán: MMR và phân bổ ngữ cảnh

### Cơ sở lựa chọn

| Phương pháp/nghiên cứu | Ý nghĩa với hệ thống này | Quyết định |
| --- | --- | --- |
| [MMR — Goldstein & Carbonell](https://aclanthology.org/X98-1025/) | Cân bằng mức liên quan với độ mới so với các kết quả đã chọn. | Thêm biến thể MMR theo thứ hạng trước rerank để hạn chế các đoạn gần trùng chiếm hết số lượt chấm. |
| [IRCoT](https://aclanthology.org/2023.acl-long.557/) | Truy xuất nhiều bước có thể tìm bằng chứng mà câu hỏi ban đầu chưa đủ để chỉ tới. | Giữ planner và truy vấn bổ sung có giới hạn hiện tại; không coi đó là triển khai đầy đủ IRCoT hoặc tái hiện benchmark của bài. |
| [Lost in the Middle](https://arxiv.org/abs/2307.03172) | Hiệu quả sử dụng bằng chứng phụ thuộc vị trí trong ngữ cảnh; tăng context không tự giải quyết việc thiếu/sử dụng sai nguồn. | Giữ ngân sách ngữ cảnh và thứ tự đọc trong tài liệu; bổ sung phân bổ luân phiên giữa các mục khi chọn nội dung. Đây là lựa chọn kỹ thuật riêng, chưa chứng minh giải quyết hiệu ứng của bài. |
| [Sufficient Context](https://research.google/pubs/sufficient-context-a-new-lens-on-retrieval-augmented-generation-systems/) | Cần phân biệt retrieval không cung cấp đủ bằng chứng với model trả lời sai dù bằng chứng đã đủ. | Thêm phép đo đủ toàn bộ các nguồn được gán nhãn; không dùng metric retrieval để kết luận câu trả lời đúng. |
| [Late Chunking](https://arxiv.org/abs/2409.04701) | Tạo vector chunk từ token embeddings đã mang ngữ cảnh của văn bản dài, trước bước pooling. | Chưa áp dụng: adapter hiện tại lấy vector theo từng chuỗi; cần pipeline token embeddings, reindex và đo trên corpus trước khi chuyển. Không thể chỉ tăng overlap và gọi đó là late chunking. |
| [RankRAG](https://arxiv.org/abs/2407.02485) | Nghiên cứu fine-tune cùng một LLM cho ranking và generation. | Grader Qwen/Llama hiện tại không được fine-tune theo RankRAG. Giữ lựa chọn hiện có; đổi model cần so sánh bằng dữ liệu có nhãn và tài nguyên máy thực tế. |

### Điểm nghẽn tìm được trong code

Reranker trước đây chỉ chấm `candidates[:RERANK_CANDIDATES]`. Nếu 32 đoạn đầu gần trùng, đoạn bổ sung ở vị trí sau đó không được chấm, ngay cả khi có thể trả lời điều kiện còn thiếu. Giới hạn tối đa ba anchor/tài liệu ở bước sau không phục hồi được ứng viên đã bị bỏ trước rerank.

Khi mở rộng phụ lục, toàn bộ các đoạn của tệp A có thể được đưa vào trước tệp B. Ngân sách ký tự có thể chỉ đủ cho A, làm mất phần bằng chứng liên quan từ B. Cảnh báo coverage giúp nhận ra thiếu nhưng không tự khắc phục phân bổ đó.

### Thay đổi đã triển khai

`app/rag/diversity.py` chọn một tập ứng viên cho rerank bằng MMR có seed:

```text
relevance(i) = 61 / (61 + i)              # i là vị trí từ 0 trong thứ hạng hybrid
similarity(a, b) = Jaccard(bigram(a), bigram(b))
score(i) = lambda * relevance(i) - (1 - lambda) * max_similarity(i, selected)
```

- Giữ nguyên một phần tư đầu danh sách, tối thiểu một đoạn. Với mặc định 32 lượt chấm, tám đoạn đầu được bảo vệ.
- Xem tối đa bốn lần số lượt chấm: mặc định tối đa 128 ứng viên. Chọn thêm lần lượt theo score, xử lý hòa điểm bằng thứ hạng gốc.
- Trả tập đã chọn theo thứ hạng gốc để các grade bằng nhau tiếp tục giữ ưu tiên hybrid. Nếu không đủ 32 ứng viên, giữ toàn bộ như trước.
- Dùng bigram từ văn bản nguồn, không lấy tên tệp làm độ mới; không cần gọi thêm embedding/LLM hoặc tải cả corpus. Đây là rank proxy và độ giống từ vựng, không phải MMR dùng cosine vector đã được calibrate.
- Không gộp, cắt hay xóa các đoạn gần giống. Những khác biệt về số liệu, phủ định và phiên bản vẫn có thể được reranker kiểm tra nếu đoạn được chọn. Tuy vậy pool hữu hạn vẫn có thể bỏ mất bằng chứng quan trọng; không có bảo đảm recall tăng cho mọi câu hỏi.

`RERANK_DIVERSITY_LAMBDA=0.75` là giá trị khởi đầu để thử nghiệm. Giá trị 1 khôi phục việc chọn top ứng viên theo thứ hạng trước rerank; giá trị thấp hơn tăng tác động của độ mới. Các backend Ollama, OpenAI public và cross-encoder dùng cùng cách chọn pool khi bật rerank. Scope guard và kiểm tra metadata/tệp nguồn chạy trước việc gửi bằng chứng cho model. Tắt rerank bỏ qua MMR.

Sau các anchor, nội dung mở rộng vẫn ưu tiên phụ lục được hỏi → phụ lục được tham chiếu → các mục chung. Trong từng nhóm ưu tiên, lấy lần lượt một đoạn của mỗi bộ `(scope, document_id, section_key)` rồi quay vòng. Giữ provenance từng đoạn, giới hạn ngân sách, cảnh báo thiếu và hai link/tài liệu. Khi dựng prompt, các đoạn đã chọn trong cùng tệp vẫn được đọc theo thứ tự chunk.

### Đo đối chứng

`complete_evidence` cho từng câu chỉ đúng khi tìm được tất cả `expected_sources`; `summary.complete_evidence_rate` lấy trung bình trên các câu có nhãn đáp án. Câu không có đáp án vẫn đo riêng bằng `retrieval_abstention_accuracy`. Nhãn phải chỉ rõ các bằng chứng thật sự cần thiết, kể cả điều kiện/ngoại lệ và tệp bổ sung. Chỉ gán nhãn tên tệp sẽ không phát hiện thiếu đoạn quan trọng trong cùng tệp.

Ví dụ định dạng JSONL dưới đây chỉ là mẫu; thay tên tệp và chỉ số bằng nguồn đã kiểm tra trên máy triển khai:

```json
{"question":"Điều kiện và ngoại lệ áp dụng là gì?","expected_sources":[{"document":"quy-dinh.pdf","chunk_index":12},{"document":"huong-dan.docx","chunk_index":7}]}
{"question":"Câu không có thông tin trong kho đã chọn","expected_sources":[]}
```

Chạy tại backend với cùng dataset, chỉ mục, model và các ngưỡng:

```powershell
# Đối chứng: top pool cũ và thứ tự mở rộng cũ.
.\venv\Scripts\python.exe -m app.evaluate questions.jsonl --expanded --model qwen2.5:7b --scope private --no-diversity --output evaluation/original-order.json
# MMR và phân bổ luân phiên.
.\venv\Scripts\python.exe -m app.evaluate questions.jsonl --expanded --model qwen2.5:7b --scope private --output evaluation/diverse.json
```

`--no-diversity` tắt cả MMR và phân bổ luân phiên cho lần đo, không thay cấu hình ứng dụng. `RERANK_DIVERSITY_LAMBDA=1` chỉ tắt MMR của ứng dụng, vẫn giữ phân bổ ngữ cảnh mới. Khi `--hybrid-only`, MMR không chạy; với `--expanded`, phân bổ ngữ cảnh vẫn chạy trừ khi thêm `--no-diversity`.

So sánh recall, complete evidence rate, precision, MRR, độ trễ và các mục còn thiếu trong coverage. `coverage.context_chars` là chi phí ký tự ước lượng của bằng chứng kèm metadata, không phải token hoặc độ dài toàn prompt. Các trường `candidate_documents`, `evidence_documents` giúp quan sát mức cạnh tranh giữa tài liệu. Planner có thể tạo truy vấn khác giữa các lần chạy; nên cố định `QUERY_EXPANSION` và kiểm tra nhiều lượt khi đánh giá. Không dùng các ví dụ tổng hợp để tuyên bố accuracy thực tế của model.

Các kiểm thử thuật toán nằm trong [test_diversity.py](../backend/tests/test_diversity.py): truy xuất đoạn bổ sung ngoài top 32, giữ nhóm ưu tiên đầu, pool có giới hạn, ID grader/cross-encoder, scope OpenAI, luân phiên phụ lục, ngân sách và metric đủ bằng chứng. Nâng cấp này không đổi embedding/chunking hoặc collection v5, không yêu cầu ingest lại dữ liệu v5.

Bộ kiểm thử backend sau nâng cấp MMR có 97 ca đạt, gồm 13 ca về đa dạng ứng viên/phân bổ ngữ cảnh/metric. Kiểm thử có mô hình giả cho grader và dữ liệu tổng hợp; không dùng kết quả này để suy ra tỷ lệ cải thiện accuracy trên corpus thực tế. MMR không làm tăng số ứng viên chấm tối đa hoặc thêm lời gọi LLM/embedding; chi phí tính bigram/Jaccard được giới hạn ở cửa sổ chọn pool.
