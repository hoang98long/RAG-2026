import shutil
import uuid
from pathlib import Path
from fastapi import HTTPException, UploadFile
from loguru import logger
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.models.models import Document
from app.rag.chunking import load_chunks
from app.rag.vector_store import get_vector_store


def upload_files(files: list[UploadFile], db: Session) -> list[Document]:
    settings = get_settings()
    settings.upload_path.mkdir(parents=True, exist_ok=True)
    saved: list[Document] = []
    pending: list[tuple[str, Path]] = []
    try:
        for file in files:
            suffix = Path(file.filename or "").suffix.lower()
            if suffix not in {".pdf", ".docx"}:
                raise HTTPException(400, f"{file.filename}: chỉ hỗ trợ PDF hoặc DOCX")
            document_id = str(uuid.uuid4())
            path = settings.upload_path / f"{document_id}{suffix}"
            pending.append((document_id, path))
            with path.open("wb") as output:
                shutil.copyfileobj(file.file, output)
            chunks = load_chunks(path)
            if not chunks:
                raise HTTPException(400, f"{file.filename}: không đọc được nội dung, PDF scan cần OCR")
            get_vector_store().add(document_id, file.filename or path.name, chunks)
            record = Document(id=document_id, filename=file.filename or path.name, filepath=str(path))
            db.add(record)
            saved.append(record)
        db.commit()
    except Exception:
        db.rollback()
        for document_id, path in pending:
            try:
                get_vector_store().delete_document(document_id)
            except Exception:
                logger.exception("Could not clean vectors for {}", document_id)
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
