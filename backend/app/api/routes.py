from pathlib import Path
from fastapi.responses import FileResponse
from app.rag.vector_store import get_vector_store
from app.core.config import get_settings
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.models import ChatHistory, Document, ReportHistory
from app.schemas.schemas import ChatRequest, DocumentOut, ReportRequest
from app.services.document_service import delete_document, upload_files
from app.services.rag_service import answer, generate_report
from app.utils.response import ok

router = APIRouter()


@router.post("/documents/upload")
def upload_documents(files: list[UploadFile] = File(...), db: Session = Depends(get_db)):
    records = upload_files(files, db)
    return ok([DocumentOut.model_validate(item).model_dump(mode="json") for item in records], "Tải tài liệu thành công")


@router.get("/documents")
def get_documents(db: Session = Depends(get_db)):
    records = db.scalars(select(Document).order_by(Document.upload_time.desc())).all()
    return ok([DocumentOut.model_validate(item).model_dump(mode="json") for item in records])


@router.delete("/documents/{document_id}")
def remove_document(document_id: str, db: Session = Depends(get_db)):
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(404, "Không tìm thấy tài liệu")
    delete_document(document, db)
    return ok(message="Đã xóa tài liệu")


@router.post("/chat")
def chat(payload: ChatRequest, db: Session = Depends(get_db)):
    result, sources, cached = answer(payload.question, db)
    return ok({"answer": result, "sources": sources, "cached": cached})


@router.post("/report")
def report(payload: ReportRequest, db: Session = Depends(get_db)):
    content, sources = generate_report(payload.template, payload.title, payload.instructions, db)
    return ok({"content": content, "sources": sources}, "Tạo báo cáo thành công")


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)):
    count = lambda model: db.scalar(select(func.count()).select_from(model)) or 0
    return ok({"documents": count(Document), "chats": count(ChatHistory), "reports": count(ReportHistory)})


def _document_file(document_id: str, db: Session) -> tuple[Document, Path]:
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(404, "Không tìm thấy tài liệu")
    path = Path(document.filepath).resolve()
    root = get_settings().upload_path.resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise HTTPException(404, "Không tìm thấy tệp tài liệu")
    return document, path


@router.get("/documents/{document_id}/file")
def document_file(document_id: str, db: Session = Depends(get_db)):
    document, path = _document_file(document_id, db)
    media_type = "application/pdf" if path.suffix.lower() == ".pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return FileResponse(path, media_type=media_type, filename=document.filename, content_disposition_type="inline")


@router.get("/documents/{document_id}/content")
def document_content(document_id: str, db: Session = Depends(get_db)):
    document, path = _document_file(document_id, db)
    chunks = get_vector_store().document_chunks(document_id)
    if not chunks:
        raise HTTPException(404, "Tài liệu chưa có nội dung trong chỉ mục hiện tại. Hãy lập lại chỉ mục theo README.")
    return ok({"id": document.id, "filename": document.filename, "file_type": path.suffix.lower()[1:], "chunks": chunks})
