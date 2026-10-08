import uuid
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


def upload_files(files: list[UploadFile], db: Session) -> list[Document]:
    settings = get_settings()
    if len(files) > settings.upload_max_files:
        raise HTTPException(400, f'Mỗi yêu cầu nhận tối đa {settings.upload_max_files} tệp')
    settings.upload_path.mkdir(parents=True, exist_ok=True)
    saved: list[Document] = []
    pending: list[tuple[str, Path]] = []
    indexed: set[str] = set()
    total_bytes = 0
    try:
        for file in files:
            suffix = Path(file.filename or '').suffix.lower()
            if suffix not in {'.pdf', '.docx'}:
                raise HTTPException(400, f'{file.filename}: chỉ hỗ trợ PDF hoặc DOCX')
            document_id = str(uuid.uuid4())
            path = settings.upload_path / f'{document_id}{suffix}'
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
                count = get_vector_store().add(document_id, file.filename or path.name, chain([first], chunks))
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
                    get_vector_store().delete_document(document_id)
            except Exception:
                logger.exception('Could not clean vectors for {}', document_id)
            path.unlink(missing_ok=True)
        raise
    for item in saved:
        db.refresh(item)
    return saved


def delete_document(document: Document, db: Session) -> None:
    get_vector_store().delete_document(document.id)
    Path(document.filepath).unlink(missing_ok=True)
    db.delete(document)
    db.commit()
