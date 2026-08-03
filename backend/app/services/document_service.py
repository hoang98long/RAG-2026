import shutil
import uuid
from pathlib import Path
from fastapi import HTTPException, UploadFile
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader, Docx2txtLoader
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.models.models import Document
from app.rag.vector_store import get_vector_store


def _load_text(path: Path) -> str:
    loader = PyPDFLoader(str(path)) if path.suffix.lower() == ".pdf" else Docx2txtLoader(str(path))
    return "\n".join(page.page_content for page in loader.load())


def upload_files(files: list[UploadFile], db: Session) -> list[Document]:
    settings = get_settings()
    settings.upload_path.mkdir(parents=True, exist_ok=True)
    splitter = RecursiveCharacterTextSplitter(chunk_size=settings.chunk_size, chunk_overlap=settings.chunk_overlap)
    saved: list[Document] = []
    try:
        for file in files:
            suffix = Path(file.filename or "").suffix.lower()
            if suffix not in {".pdf", ".docx"}:
                raise HTTPException(400, f"{file.filename}: chỉ hỗ trợ PDF hoặc DOCX")
            document_id = str(uuid.uuid4())
            path = settings.upload_path / f"{document_id}{suffix}"
            with path.open("wb") as output:
                shutil.copyfileobj(file.file, output)
            chunks = splitter.split_text(_load_text(path))
            if not chunks:
                path.unlink(missing_ok=True)
                raise HTTPException(400, f"{file.filename}: không đọc được nội dung")
            get_vector_store().add(document_id, file.filename or path.name, chunks)
            record = Document(id=document_id, filename=file.filename or path.name, filepath=str(path))
            db.add(record)
            saved.append(record)
        db.commit()
        for item in saved:
            db.refresh(item)
        return saved
    except Exception:
        db.rollback()
        raise


def delete_document(document: Document, db: Session) -> None:
    get_vector_store().delete_document(document.id)
    Path(document.filepath).unlink(missing_ok=True)
    db.delete(document)
    db.commit()
