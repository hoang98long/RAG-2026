# Triển khai thử nghiệm cho khách hàng

Hướng dẫn này dành cho một máy triển khai, một process backend và Chroma nhúng. Giữ nguyên project Compose, volumes và `.env` của máy đã ingest. Không chạy `down -v`, không sao chép DB từ máy phát triển vào máy khách hàng. Đọc [quy trình bảo toàn dữ liệu](STORAGE_DEPLOYMENT.md) trước lần cập nhật chuyển dữ liệu từ Git tracked sang ignored.

## 1. Chuẩn bị cấu hình và dữ liệu

- Máy mới: tạo `.env` từ mẫu tương ứng; chạy Compose dùng `.env` gốc, chạy Python trực tiếp dùng `backend/.env`. Máy đã triển khai: giữ tệp hiện có, bổ sung biến còn thiếu. `.env.example` không phải cấu hình đang chạy.
- Điền `INTERNAL_ACCESS_TOKEN` ngẫu nhiên, dài 32–512 ký tự. Có thể sinh bằng `python -c "import secrets; print(secrets.token_urlsafe(32))"`. Không đưa khóa vào Git, URL hoặc biến `VITE_*`. Khóa trống sẽ khóa private, upload, xóa và báo cáo. Đây là quyền quản trị nội bộ dùng chung, chưa có tài khoản hay phân quyền từng khách hàng.
- Giữ `LLM_MODEL=qwen2.5:7b` và embedding đang dùng. Chỉ chọn Llama 70B khi máy đủ RAM/VRAM và đã thử thời gian trả lời. Thay LLM không cần reindex; thay embedding, chunking hoặc query instruction cần kế hoạch reindex riêng.
- OpenAI tùy chọn: điền `OPENAI_API_KEY` trên backend. Không có key vẫn dùng local. OpenAI chỉ truy xuất kho public; tài liệu nội bộ đưa vào kho private. Xác nhận nội dung được phép công khai trước khi upload public.
- Cho người ngoài truy cập: cấu hình HTTPS tại ingress/reverse proxy, `SESSION_COOKIE_SECURE=true`, `CORS_ORIGINS=https://ten-mien-thuc-te` (đúng origin, không có dấu `/` cuối). Chỉ công khai frontend/ingress. Giữ backend và Ollama trong mạng được bảo vệ. Nếu cần giữ IP khách qua ingress, cấu hình danh sách proxy tin cậy tại Nginx; mặc định có thể tính hạn mức chung cho nhiều khách qua cùng NAT/proxy.
- Dừng các tiến trình ghi khi sao lưu. Sao lưu đồng bộ metadata, Chroma/FTS và upload của **cả hai kho**, cùng cấu hình riêng. Kiểm tra phục hồi vào môi trường tách biệt trước buổi thử nghiệm.

## 2. Khởi động hoặc cập nhật bằng Compose

Chạy ở gốc repository, với cùng project Compose của lần triển khai trước:

```bash
docker compose config --quiet
docker compose up -d --build --wait --wait-timeout 180
docker compose exec ollama ollama pull qwen2.5:7b
docker compose exec ollama ollama pull qwen3-embedding:0.6b
# Tùy chọn; không cần để Qwen hoạt động:
# docker compose exec ollama ollama pull llama3.1:70b
docker compose ps
```

Không chạy reindex trong quy trình cập nhật thông thường. Chỉ migration chỉ mục cũ hoặc chủ động thay embedding/chunking mới cần [quy trình reindex](../README.md#lưu-trữ-cập-nhật-và-reindex). Không chạy đồng thời API ghi và reindex. Nếu còn service Chroma từ Compose cũ, dừng service đó theo STORAGE_DEPLOYMENT.md; giữ volume.

Compose có healthcheck API và frontend, frontend đợi API healthy, restart `unless-stopped`, giới hạn log Docker 3 tệp × 10 MB mỗi service chính. API có thời gian dừng tối đa 10 phút để hoàn tất request; vẫn nên chờ upload/chat hoàn tất trước khi cập nhật. Trạng thái `unhealthy` **không tự khởi động lại container**; restart policy áp dụng khi process thoát. Không thêm nhiều worker hoặc replicas khi vẫn dùng session/rate limit trong bộ nhớ và Chroma nhúng.

Nginx phân giải lại tên backend trong mạng Docker khi container đổi IP; không tự retry POST sang upstream khác. Kiểm tra cấu hình thực tế bằng `docker compose exec frontend nginx -t`. Vào `http://localhost:3000` để kiểm tra nội bộ; dùng URL HTTPS thực tế khi thử với khách hàng.

## 3. Kiểm tra trước buổi thử nghiệm

| Kiểm tra | Ý nghĩa |
| --- | --- |
| `GET /api/health` | API còn phục vụ HTTP; không gọi mô hình hoặc mở kho tài liệu |
| `GET /api/ready` | 200 khi Ollama truy cập được và có embedding + LLM mặc định; 503 khi thiếu phụ thuộc |
| `GET /api/chat/models` | Trạng thái từng lựa chọn mô hình; không công bố đường dẫn, nội dung hay số lượng tài liệu private |
| `python -m app.preflight --scope all` | Kiểm tra cấu hình quyền, phụ thuộc và đối chiếu metadata/tệp/FTS hiện tại, chỉ đọc |

Qua frontend `/api/...`; gọi trực tiếp backend thì bỏ `/api`. Ví dụ:

```bash
curl --fail http://localhost:3000/api/health
curl --fail http://localhost:3000/api/ready
docker compose exec backend python -m app.preflight --scope all
```

Chạy Python trực tiếp: vào thư mục `backend`, kích hoạt môi trường Python rồi chạy cùng lệnh `python -m app.preflight`. Có thể chọn `--scope public`/`private`, hoặc `--skip-models` để chỉ kiểm tra lưu trữ/quyền mà không gọi Ollama. Lệnh không in key, nội dung hoặc tên/đường dẫn tệp. Exit code 0 là các kiểm tra đã chọn đạt; 1 là cần kiểm tra JSON `issue`. Lệnh không sửa, xóa, reindex hay khởi tạo Chroma.

Nên chạy lúc không có upload/xóa/reindex để tránh kết quả không nhất quán giữa các bước đọc. Lệnh hỗ trợ metadata SQLite; không kiểm tra nội dung vector hoặc sửa DB hỏng. Khi có tài liệu, kiểm tra sự tồn tại của Chroma DB, trạng thái FTS và từng document trong FTS hiện tại; đây không phải kiểm chứng đồng bộ đầy đủ giữa FTS và vector.

| `issue` | Xử lý |
| --- | --- |
| `metadata_missing_verify_storage_path` | Kiểm tra mount/đường dẫn. Máy mới chưa tạo kho có thể gặp trạng thái này; mở thư viện/upload đúng kho rồi chạy lại. Máy cũ không tự ingest lại trước khi xác định dữ liệu ở đâu. |
| `storage_mismatch` | Xem các bộ đếm `files_missing`, `files_outside_root`, `unindexed_documents`, `orphan_index_documents`; kiểm tra backup và cấu hình trước khi sửa. |
| `lexical_rebuild_pending` | Kiểm tra lần ingest/reindex trước có bị dừng giữa chừng; backup rồi xử lý theo hướng dẫn chỉ mục. |
| `vector_database_missing` | Metadata có tài liệu nhưng thiếu Chroma DB ở đường dẫn cấu hình; kiểm tra mount/backup. |
| `storage_check_failed` / `metadata_integrity_failed` | Không tiếp tục ghi cho tới khi kiểm tra DB và bản sao lưu; lệnh không tự sửa. |
| `empty_corpus` | Kho trống là trạng thái hợp lệ về kỹ thuật; phải có tài liệu phù hợp trong kho dự kiến demo để trả lời được. |

Inventory Ollama được cache tối đa 15 giây khi thành công, 3 giây khi lỗi; giao diện chat kiểm tra lại mỗi 30 giây hoặc bấm **Kiểm tra lại**. Danh sách mô hình chỉ xác nhận đã tải model, chưa xác nhận đủ RAM/VRAM hoặc inference thành công. OpenAI hiển thị đã cấu hình key/embedding, **chưa xác nhận key hợp lệ, quyền model, kết nối và hạn mức** cho đến khi gọi API. `/ready` không kiểm tra nội dung kho, TLS hay chất lượng câu trả lời; vẫn cần các bước dưới đây.

## 4. Nghiệm thu luồng sử dụng

1. Cửa sổ ẩn danh: chỉ có public; không có nút quản lý. Gọi private/all trực tiếp phải nhận 401. Nếu phiên đăng nhập không kiểm tra được, giao diện hiện **Kết nối lại** thay vì giả định backend chưa cấu hình khóa.
2. Đăng nhập nội bộ, upload một PDF có lớp chữ hoặc DOCX vào private và một tài liệu được phép công khai vào public. Không dùng tài liệu thực sự nhạy cảm để demo ranh giới bảo mật. Tạo hai dữ kiện phân biệt để dễ đối chiếu.
3. Dùng Qwen hỏi một dữ kiện, một phủ định/điều kiện áp dụng, một số/mã và một câu hỏi cần nhiều đoạn. Mở từng nguồn: đúng kho, tệp, trang/đoạn và nội dung. Trong câu trả lời không hiện mã S1/S2; tối đa hai nguồn hiển thị cho mỗi tài liệu.
4. Từ phiên public và OpenAI public nếu đã cấu hình, hỏi về dữ kiện chỉ có trong private: không được trả dữ kiện private. Kiểm tra thêm câu hỏi cố yêu cầu bỏ quy tắc/chuyển kho. Local được dùng public hoặc cả hai khi đã đăng nhập; OpenAI private/all phải bị chặn.
5. Hỏi một câu ngoài tài liệu: phải báo chưa đủ nguồn/bằng chứng. Lập bảng câu hỏi–đáp án chuẩn, gồm trường hợp diễn đạt lại và yêu cầu danh sách đầy đủ; ghi nhận đúng/sai/thiếu và độ trễ. Không dùng số lượng test phần mềm làm số đo accuracy.
6. Thử upload lại khi mạng bị ngắt trong cùng phiên, tài liệu hỏng/scan, tên tệp dài, xóa tài liệu public, đăng xuất và đăng xuất ở tab khác. Không để thông báo thành công khi request thất bại. Kiểm tra desktop lẫn điện thoại, vùng cuộn chat và link nguồn.
7. Khởi động lại backend trong giờ bảo trì: phiên nội bộ cũ hết hiệu lực, đăng nhập lại; dữ liệu vẫn tồn tại trong volumes. Dừng Ollama để kiểm tra thông báo thiếu phụ thuộc, bật lại rồi kiểm tra phục hồi. Thao tác gây gián đoạn này chỉ thực hiện trên môi trường thử nghiệm.

Gửi request đầu trước giờ demo để đo thời gian nạp model; không coi một lần probe inventory là warm-up. Lưu thời gian P50/P95, cấu hình máy và số người dùng đồng thời thực tế; bắt đầu với tải nhỏ rồi tăng có kiểm soát. Pipeline kiểm chứng nhiều bước có thể lâu hơn một lượt chat LLM trực tiếp. Chỉ kết luận đáp ứng độ trễ/độ chính xác của khách hàng sau khi đo trên tài liệu thật đã được phép sử dụng.

## 5. Theo dõi và xử lý sự cố

Mỗi response API có `X-Request-ID` do server sinh. Lỗi bất ngờ trả thông báo chung kèm mã tra cứu; dùng mã này tìm log. Log ứng dụng ghi method, mẫu route, status, thời gian xử lý; không ghi câu hỏi/body/query string trong bản ghi request. Lỗi provider không được ghi toàn bộ payload hoặc local variables. Log xoay 10 MB, giữ 7 ngày trong container; stdout xuất được qua `docker compose logs --tail 200 backend`. Cần chuyển log ra hệ thống lưu trữ riêng nếu muốn giữ qua lần tạo lại container. Không gửi `.env`, key hay nội dung private khi báo lỗi.

- 401: đăng nhập lại, kiểm tra cookie HTTPS và origin; restart backend sẽ thu hồi phiên trong bộ nhớ.
- 403: kiểm tra quyền/scope/Origin, không mở private để khắc phục yêu cầu OpenAI.
- 409 nguồn: hỏi lại để lấy link hiện tại; không sửa link sang kho khác. 409 upload: không tái sử dụng cùng mã cho tệp khác.
- 413: giảm dung lượng/số tệp; đồng bộ giới hạn backend, Nginx và ingress. PDF scan cần OCR trước upload.
- 429: chờ số giây được thông báo; giảm số câu hỏi đồng thời. Không tự retry thao tác ghi vì có thể tạo tải lặp.
- 503/504: kiểm tra trạng thái model/embedding, RAM/VRAM và kết nối; không tăng timeout để thay thế việc đo tài nguyên.
- Câu trả lời thiếu nguồn: kiểm tra đúng scope, dữ liệu/index v5 và tập câu hỏi chuẩn. Các endpoint danh sách đều có giới hạn; `/documents` tương thích cũ tối đa 200 mục, nên dùng `/documents/paged` để phân trang đầy đủ.

Nếu cần rollback: dừng tiến trình ghi, dùng bản code/image đã ghi nhận, giữ nguyên volumes nếu storage tương thích; nếu đã migration dữ liệu thì phục hồi **cả bộ** metadata/vector/FTS/upload tương ứng từ backup. Không trộn index của bản này với metadata/upload của bản khác. Kiểm tra lại public/private, nguồn và một câu hỏi chuẩn trước khi mở cho khách hàng.

Tham chiếu triển khai: [Docker Compose healthcheck và restart](https://docs.docker.com/reference/compose-file/services/), [Nginx proxy_pass, rewrite và resolver](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_pass), [Ollama inventory API](https://docs.ollama.com/api/tags).

## Kết quả kiểm chứng tại workspace (20/10/2026)

- 131 kiểm thử backend, 14 kiểm thử tiện ích frontend và 22 kịch bản Edge đạt; build frontend production thành công.
- Luồng API ingest/RAG/nguồn/xóa dùng DOCX, SQLite, Chroma và FTS thật trong thư mục tạm; model và embedding giả lập. Kiểm tra upload retry không nhân đôi chỉ mục, public không mở private DB, reviewer trích dẫn, fingerprint nguồn và xóa đúng kho.
- Edge nối API thật đã kiểm tra đăng nhập/đăng xuất, cookie HttpOnly, thu hồi phiên, public/private và thông báo mô hình mất kết nối. Không dùng key OpenAI hay model thật.
- `docker compose config --quiet` đạt. Docker daemon tại workspace chưa chạy, nên chưa build/chạy các image, kiểm tra Nginx/TLS hoặc đo hiệu năng phần cứng triển khai. Không có kết quả benchmark accuracy trên tài liệu khách hàng trong lượt này.

Các bước nghiệm thu ở trên là phần cần chạy tại môi trường triển khai; kết quả kiểm thử phần mềm không thay thế các bước đó.
