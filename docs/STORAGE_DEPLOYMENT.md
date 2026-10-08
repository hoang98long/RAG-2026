# Giữ dữ liệu riêng khi cập nhật code

Git chỉ lưu code và các file cấu hình mẫu. Dữ liệu thuộc về từng máy triển khai:

| Dữ liệu | Chạy trực tiếp, cấu hình mặc định | Docker Compose hiện tại |
| --- | --- | --- |
| Metadata tài liệu, lịch sử chat/báo cáo | `backend/rag.db` | Volume `uploads`, `/app/storage/rag.db` |
| Vector Chroma và chỉ mục từ khóa FTS | `backend/chroma_data/` | Volume `chroma_data`, `/app/chroma_data/` |
| PDF/DOCX gốc | `backend/storage/uploads/` | Volume `uploads`, `/app/storage/uploads/` |
| Cấu hình riêng | `backend/.env` | `.env` ở gốc cho Compose |

`.gitignore` loại cả database SQLite và các file WAL/SHM/journal, toàn bộ thư mục dữ liệu, log và `.env` riêng. `backend/.dockerignore` loại dữ liệu khỏi build context để `COPY . .` không đưa dữ liệu máy phát triển vào image.

Giữ nguyên `DATABASE_URL`, `CHROMA_DIR`, `UPLOAD_DIR` và đường dẫn hiện tại trên máy đã ingest. Không thay `.env` bằng `.env.example`; không sao chép DB/upload/index từ máy phát triển sang máy triển khai. Không thay đổi đường dẫn mặc định hay tự di chuyển dữ liệu trong nâng cấp này.

## Lần cập nhật đầu tiên khi dữ liệu từng được Git theo dõi

**Commit bỏ theo dõi dữ liệu sẽ ghi nhận việc xóa các tệp khỏi repository. Khi máy khác pull commit đó, Git có thể xóa bản tệp đang được theo dõi hoặc từ chối pull vì DB đã thay đổi. `.gitignore` không bảo vệ tệp đang được theo dõi trong bước chuyển đổi này.**

1. Dừng backend, quá trình ingest/reindex và mọi process dùng cùng database/index.
2. Sao lưu database, toàn bộ Chroma/FTS và upload của **chính máy triển khai** vào thư mục ngoài checkout. Sao lưu cả WAL/SHM/journal nếu có; giữ `.env` riêng. Với đường dẫn tùy chỉnh, sao lưu đúng các đường dẫn đang sử dụng.
3. Kiểm tra bản sao đã đủ và đọc được. Giải quyết/commit riêng các thay đổi code trước khi pull. Không dùng `git reset --hard` hoặc `git clean -fdx`.
4. Nếu dữ liệu cũ còn được theo dõi và có thay đổi cục bộ, chỉ sau khi sao lưu thành công mới đưa các đường dẫn dữ liệu được theo dõi về bản HEAD để Git có thể pull. Bản dữ liệu triển khai sẽ được khôi phục từ backup sau đó.
5. Pull code, khôi phục dữ liệu máy triển khai từ backup vào đúng vị trí cũ **trước khi khởi động backend**. Kiểm tra `git ls-files` không còn dữ liệu và `.env` vẫn trỏ đúng đường dẫn.

Ví dụ PowerShell, chạy ở gốc repository trên máy triển khai, dùng đường dẫn mặc định. Backend phải được dừng trước. Đoạn này chỉ dành cho lần chuyển dữ liệu từ tracked sang ignored; nếu có đường dẫn riêng, điều chỉnh danh sách sao lưu trước khi chạy.

```powershell
$ErrorActionPreference = 'Stop'
$projectRoot = (Get-Location).Path
$backupRoot = Join-Path (Split-Path $projectRoot -Parent) ('rag-backup-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
$backupBackend = Join-Path $backupRoot 'backend'
New-Item -ItemType Directory -Path $backupBackend | Out-Null

# Bao gom DB va cac file SQLite sidecar; thu muc duoc copy de quy.
$runtimePaths = @('backend/chroma_data', 'backend/storage', 'backend/.env')
$runtimePaths += @(Get-ChildItem -LiteralPath 'backend' -File |
  Where-Object { $_.Name -match '\.(db|sqlite|sqlite3)(-.*)?$' } |
  ForEach-Object { 'backend/' + $_.Name })
foreach ($relative in $runtimePaths) {
  $source = Join-Path $projectRoot $relative
  if (Test-Path -LiteralPath $source) {
    Copy-Item -LiteralPath $source -Destination $backupBackend -Recurse -Force
  }
}
Write-Output "Backup: $backupRoot"

# Kiem tra backup truoc khi tiep tuc: can DB + Chroma + cac tep goc cua may nay.
Get-ChildItem -LiteralPath $backupBackend -Recurse
```

Sau khi đã kiểm tra bản sao, tiếp tục **trong cùng terminal**:

```powershell
try {
  $trackedRuntime = @(git ls-files -- backend/rag.db backend/chroma_data backend/storage)
  if ($LASTEXITCODE -ne 0) { throw 'Khong doc duoc danh sach tep Git' }
  if ($trackedRuntime.Count -gt 0) {
    # Chi reset ban worktree cua du lieu cu; backup o ngoai repo da duoc kiem tra.
    git restore --source=HEAD --worktree -- $trackedRuntime
    if ($LASTEXITCODE -ne 0) { throw 'Khong the chuan bi du lieu tracked cho pull' }
  }
  git pull --ff-only
  if ($LASTEXITCODE -ne 0) { throw 'Pull that bai; giai quyet thay doi code truoc khi thu lai' }
} finally {
  # Luon tra lai du lieu rieng, ke ca khi pull that bai.
  foreach ($entry in Get-ChildItem -LiteralPath $backupBackend -Force) {
    Copy-Item -LiteralPath $entry.FullName -Destination (Join-Path $projectRoot 'backend') -Recurse -Force
  }
}
git ls-files -- backend/rag.db backend/chroma_data backend/storage
# Phai khong co ket qua truoc khi khoi dong lai backend.
```

Không chạy khối thứ hai nếu backup chưa đủ, backend chưa dừng, có thay đổi đã stage trong các tệp dữ liệu, hoặc các đường dẫn đang sử dụng khác ví dụ. Trên Linux làm cùng quy trình: dừng dịch vụ, sao chép giữ nguyên cấu trúc/quyền bằng `cp -a` vào thư mục ngoài checkout, kiểm tra, pull và khôi phục trước khi khởi động. Đây không phải hướng dẫn tự động áp dụng cho mọi cấu hình triển khai.

## Những lần cập nhật tiếp theo

Sau khi dữ liệu đã được bỏ theo dõi trên máy triển khai, `git pull` cập nhật code và không đồng bộ dữ liệu giữa các máy. Không force-add các thư mục dữ liệu. Dừng backend khi cập nhật và duy trì backup theo lịch riêng.

Với Compose, tiếp tục dùng cùng thư mục/project Compose và các volume hiện có, rồi `docker compose up -d --build`. Không chạy `docker compose down -v`: tùy chọn `-v` xóa named volume. Nếu đổi tên/thư mục project, chỉ rõ cùng tên project bằng `-p` hoặc `COMPOSE_PROJECT_NAME`; nếu không, Compose có thể chọn volume mới khiến ứng dụng trông như mất dữ liệu. Không đổi tên volume để áp dụng nâng cấp này.

Các tệp tracked trong checkout và dữ liệu đang nằm trong named volume là hai nơi khác nhau. Khi dùng Compose hiện tại, backup volume `uploads` và `chroma_data` đang sử dụng sau khi dừng các process ghi; khôi phục volume nếu cần. Không copy `backend/rag.db` của checkout đè lên DB trong volume.

Rebuild image không tự ingest lại. Reindex chỉ cần khi đổi pipeline/embedding/chunking và phải đọc tài liệu **trên máy triển khai**. Việc nâng cấp pipeline v4 trước đó vẫn cần reindex nếu máy đang dùng collection v2/v3; bỏ theo dõi Git không tự chuyển đổi chỉ mục. Đổi đường dẫn có thể mở DB/collection rỗng: kiểm tra đường dẫn trước khi ingest lại. DB hiện lưu `filepath` của tài liệu, nên nếu chủ động di chuyển upload cần cập nhật metadata tương ứng, không chỉ đổi `UPLOAD_DIR`.

Xóa dữ liệu khỏi tracking không xóa các bản đã commit khỏi lịch sử Git. Nếu tài liệu chứa nội dung không được phép công khai và từng commit, cần xử lý lịch sử riêng trước khi đưa repository lên GitHub.

Tham khảo: [Git gitignore](https://git-scm.com/docs/gitignore), [Git rm --cached](https://git-scm.com/docs/git-rm).
