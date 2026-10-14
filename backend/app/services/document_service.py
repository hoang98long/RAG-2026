import uuid
import hashlib
from contextlib import contextmanager
from threading import Lock, RLock
from weakref import WeakValueDictionary
from itertools import chain
from pathlib import Path
from zipfile import BadZipFile
from xml.etree.ElementTree import ParseError
from pypdf.errors import PdfReadError
from fastapi import HTTPException, UploadFile
from loguru import logger
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.models.models import Document
from app.rag.chunking import iter_chunks
from app.rag.vector_store import get_vector_store


def _copy_upload(file: UploadFile, path: Path, max_bytes: int) -> int:
    size = 0
    if file.size is not None and file.size > max_bytes:
        raise HTTPException(413, f'{file.filename}: tệp vượt dung lượng tối đa {max_bytes // (1024 * 1024)} MiB')
    with path.open('wb') as output:
        while block := file.file.read(1024 * 1024):
            size += len(block)
            if size > max_bytes:
                raise HTTPException(413, f'{file.filename}: tệp vượt dung lượng tối đa {max_bytes // (1024 * 1024)} MiB')
            output.write(block)
    return size


def _read_chunks(path: Path, filename: str):
    try:
        yield from iter_chunks(path)
    except (PdfReadError, BadZipFile, ParseError, KeyError, ValueError) as exc:
        raise HTTPException(400, f'{filename}: không đọc được tệp. Kiểm tra tệp hỏng hoặc PDF có mật khẩu; hãy xuất lại bản không khóa.') from exc


def _upload_files(files: list[UploadFile], db: Session, scope: str = "private", request_id: str | None = None) -> list[Document]:
    settings = get_settings()
    if len(files) > settings.upload_max_files:
        raise HTTPException(400, f'Mỗi yêu cầu nhận tối đa {settings.upload_max_files} tệp')
    upload_path = settings.scope_upload_path(scope)
    upload_path.mkdir(parents=True, exist_ok=True)
    saved: list[Document] = []
    pending: list[tuple[str, Path]] = []
    indexed: set[str] = set()
    total_bytes = 0
    try:
        for file in files:
            suffix = Path(file.filename or '').suffix.lower()
            if suffix not in {'.pdf', '.docx'}:
                raise HTTPException(400, f'{file.filename}: chỉ hỗ trợ PDF hoặc DOCX')
            document_id = request_id or str(uuid.uuid4())
            path = upload_path / f'{document_id}{suffix}'
            pending.append((document_id, path))
            total_bytes += _copy_upload(file, path, settings.upload_max_file_mb * 1024 * 1024)
            if total_bytes > settings.upload_max_request_mb * 1024 * 1024:
                raise HTTPException(413, 'Tổng dung lượng tệp vượt giới hạn yêu cầu upload')
            chunks = iter(_read_chunks(path, file.filename or path.name))
            first = next(chunks, None)
            if first is None:
                raise HTTPException(400, f'{file.filename}: không trích xuất được chữ. PDF có thể là bản scan/ảnh hoặc có lớp chữ không đọc được. Hãy chạy OCR rồi tải lại bản PDF có thể tìm kiếm văn bản.')
            indexed.add(document_id)
            try:
                count = (get_vector_store() if scope == "private" else get_vector_store("public")).add(document_id, file.filename or path.name, chain([first], chunks))
            finally:
                chunks.close()
            logger.info('Indexed {}: {} chunks', file.filename, count)
            record = Document(id=document_id, filename=file.filename or path.name, filepath=str(path))
            db.add(record)
            saved.append(record)
        db.commit()
    except Exception as exc:
        if isinstance(exc, HTTPException):
            logger.warning('Upload rejected ({}): {}', exc.status_code, exc.detail)
        else:
            logger.exception('Document upload failed')
        db.rollback()
        for document_id, path in pending:
            try:
                if document_id in indexed:
                    (get_vector_store() if scope == "private" else get_vector_store("public")).delete_document(document_id)
            except Exception:
                logger.exception('Could not clean vectors for {}', document_id)
            path.unlink(missing_ok=True)
        raise
    for item in saved:
        db.refresh(item)
    return saved


def delete_document(document: Document, db: Session, scope: str = "private") -> None:
    path = Path(document.filepath).resolve()
    if not path.is_relative_to(get_settings().scope_upload_path(scope).resolve()):
        raise HTTPException(403, 'Đã chặn xóa tệp không thuộc kho tài liệu đã chọn')
    (get_vector_store() if scope == "private" else get_vector_store("public")).delete_document(document.id)
    path.unlink(missing_ok=True)
    db.delete(document)
    db.commit()


_request_locks = WeakValueDictionary()
_request_locks_guard = Lock()


@contextmanager
def _request_lock(scope: str, request_id: str):
    key = (scope, request_id)
    with _request_locks_guard:
        lock = _request_locks.get(key)
        if lock is None:
            lock = RLock()
            _request_locks[key] = lock
    with lock:
        yield


def _hash_stream(stream, max_bytes: int) -> str:
    digest, used = hashlib.sha256(), 0
    while block := stream.read(1024 * 1024):
        used += len(block)
        if used > max_bytes:
            raise HTTPException(413, 'Tệp vượt giới hạn dung lượng')
        digest.update(block)
    return digest.hexdigest()


def upload_files(files: list[UploadFile], db: Session, scope: str = "private", request_id: str | None = None) -> list[Document]:
    if request_id is None:
        return _upload_files(files, db, scope)
    try:
        request_id = str(uuid.UUID(request_id))
    except ValueError as exc:
        raise HTTPException(400, 'Mã yêu cầu upload không hợp lệ') from exc
    if len(files) != 1:
        raise HTTPException(400, 'Mã upload chỉ hỗ trợ một tệp trong mỗi yêu cầu')
    with _request_lock(scope, request_id):
        existing = db.get(Document, request_id)
        if existing is not None:
            settings = get_settings()
            path = Path(existing.filepath).resolve()
            if (not path.is_relative_to(settings.scope_upload_path(scope).resolve()) or not path.is_file()
                    or existing.filename != files[0].filename):
                raise HTTPException(409, 'Mã upload đã thuộc tệp khác hoặc tệp nguồn không còn')
            max_bytes = settings.upload_max_file_mb * 1024 * 1024
            files[0].file.seek(0)
            incoming = _hash_stream(files[0].file, max_bytes)
            with path.open('rb') as original:
                original_hash = _hash_stream(original, max_bytes)
            if incoming != original_hash:
                raise HTTPException(409, 'Mã upload đã được dùng với nội dung tệp khác')
            return [existing]
        return _upload_files(files, db, scope, request_id)
