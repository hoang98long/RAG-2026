from pathlib import Path
from typing import Literal
import hashlib
from fastapi.responses import FileResponse
from app.rag.vector_store import get_vector_store
from app.core.config import get_settings
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, Query, Header, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.core.database import get_db, get_scope_db, get_private_db
from app.core.access import require_private_access
from app.core.public_limits import public_chat_slot
from app.models.models import ChatHistory, Document, ReportHistory
from app.schemas.schemas import ChatRequest, DocumentOut, ReportRequest
from app.services.document_service import delete_document, upload_files
from app.services.rag_service import answer, generate_report
from app.utils.response import ok

Scope = Literal['private', 'public']
router = APIRouter()


def _store(scope: Scope):
    return get_vector_store() if scope == 'private' else get_vector_store('public')


def _record(item, scope):
    return {**DocumentOut.model_validate(item).model_dump(mode='json'), 'scope': scope}


@router.post('/documents/upload', dependencies=[Depends(require_private_access)])
def upload_documents(files: list[UploadFile] = File(...), scope: Scope = Query('private'), db: Session = Depends(get_scope_db),
                     request_id: str | None = Header(None, alias='Idempotency-Key', max_length=36)):
    records = upload_files(files, db, scope=scope, request_id=request_id)
    return ok([_record(item, scope) for item in records], 'Tải tài liệu thành công')


@router.get('/documents')
def get_documents(scope: Scope = Query('private'), db: Session = Depends(get_scope_db),
                  offset: int = Query(0, ge=0), limit: int = Query(200, ge=1, le=200)):
    records = db.scalars(select(Document).order_by(Document.upload_time.desc(), Document.id).offset(offset).limit(limit)).all()
    return ok([_record(item, scope) for item in records])


@router.delete('/documents/{document_id}', dependencies=[Depends(require_private_access)])
def remove_document(document_id: str, scope: Scope = Query('private'), db: Session = Depends(get_scope_db)):
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(404, 'Không tìm thấy tài liệu trong kho đã chọn')
    delete_document(document, db, scope=scope)
    return ok(message='Đã xóa tài liệu')


def get_chat_db(request: Request, payload: ChatRequest):
    if payload.scope == 'public':
        with public_chat_slot(request):
            yield None
    else:
        require_private_access(request)
        yield from get_db()


@router.post('/chat')
def chat(payload: ChatRequest, db: Session | None = Depends(get_chat_db)):
    result, sources, cached, coverage = answer(payload.question, db, model=payload.model, scope=payload.scope)
    return ok({'answer': result, 'sources': sources, 'cached': cached, 'coverage': coverage,
               'model': payload.model, 'scope': payload.scope})


@router.get('/chat/models')
def chat_models():
    from app.services.readiness import model_status
    models, _ = model_status(get_settings())
    return ok(models)


@router.post('/report')
def report(payload: ReportRequest, db: Session = Depends(get_private_db)):
    result = generate_report(payload.template, payload.title, payload.instructions, db,
                             model=payload.model, document_ids=payload.document_ids, sections=payload.sections)
    content, sources = result
    return ok({'content': content, 'sources': sources, 'sections': getattr(result, 'sections', []),
               'coverage': getattr(result, 'coverage', {}), 'model': payload.model, 'scope': 'private'},
              'Đã xử lý yêu cầu báo cáo')


@router.get('/dashboard')
def dashboard(scope: Scope = Query('private'), db: Session = Depends(get_scope_db)):
    count = lambda model: db.scalar(select(func.count()).select_from(model)) or 0
    return ok({'documents': count(Document), 'chats': count(ChatHistory), 'reports': count(ReportHistory)})


def _document_file(document_id: str, db: Session, scope: Scope = 'private') -> tuple[Document, Path]:
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(404, 'Không tìm thấy tài liệu trong kho đã chọn')
    path = Path(document.filepath).resolve()
    root = get_settings().scope_upload_path(scope).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise HTTPException(404, 'Không tìm thấy tệp tài liệu trong kho đã chọn')
    return document, path


@router.get('/documents/{document_id}/file')
def document_file(document_id: str, scope: Scope = Query('private'), db: Session = Depends(get_scope_db)):
    document, path = _document_file(document_id, db, scope)
    media_type = 'application/pdf' if path.suffix.lower() == '.pdf' else 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    return FileResponse(path, media_type=media_type, filename=document.filename, content_disposition_type='inline')


@router.get('/documents/{document_id}/content')
def document_content(document_id: str, db: Session = Depends(get_scope_db), scope: Scope = Query('private'),
                     offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200),
                     chunk: int | None = Query(None, ge=0), page: int | None = Query(None, ge=1),
                     version: str | None = Query(None, max_length=100), digest: str | None = Query(None, max_length=64)):
    document, path = _document_file(document_id, db, scope)
    store = _store(scope)
    if version is not None and version != store.collection.name:
        raise HTTPException(409, 'Nguồn thuộc chỉ mục cũ. Hãy hỏi lại để lấy nguồn hiện tại.')
    result = store.document_page(document_id, offset=offset, limit=limit, chunk_index=chunk, page=page)
    if not result['total']:
        raise HTTPException(404, 'Tài liệu chưa có nội dung trong chỉ mục hiện tại. Hãy lập lại chỉ mục theo README.')
    if digest is not None:
        target = next((item for item in result['chunks'] if item['chunk_index'] == chunk), None)
        if target is None or hashlib.sha256(target['content'].encode()).hexdigest()[:16] != digest:
            raise HTTPException(409, 'Nội dung đoạn nguồn đã thay đổi. Hãy hỏi lại để lấy nguồn hiện tại.')
    return ok({'id': document.id, 'filename': document.filename, 'file_type': path.suffix.lower()[1:], 'scope': scope, **result})


@router.get('/documents/upload-limits')
def upload_limits():
    settings = get_settings()
    return ok({'max_file_mb': settings.upload_max_file_mb, 'max_request_mb': settings.upload_max_request_mb,
               'max_files': settings.upload_max_files})


@router.get('/documents/paged')
def document_catalogue(db: Session = Depends(get_scope_db), scope: Scope = Query('private'), offset: int = Query(0, ge=0),
                       limit: int = Query(50, ge=1, le=200), q: str = Query('', max_length=100)):
    predicate = Document.filename.contains(q.strip(), autoescape=True) if q.strip() else True
    total = db.scalar(select(func.count()).select_from(Document).where(predicate)) or 0
    records = db.scalars(select(Document).where(predicate).order_by(Document.upload_time.desc(), Document.id).offset(offset).limit(limit)).all()
    return ok({'items': [_record(item, scope) for item in records], 'total': total, 'offset': offset, 'limit': limit})
