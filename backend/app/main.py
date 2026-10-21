from contextlib import asynccontextmanager
from time import perf_counter
from uuid import uuid4
from pathlib import Path
from sqlalchemy.engine import make_url
from fastapi.responses import JSONResponse
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from app.api.routes import router
from app.api.auth import router as auth_router
from app.api.health import router as health_router
from app.core.config import get_settings
from app.core.access import ProtectedWriteMiddleware
from app.core.model_errors import register_model_errors
from app.core.upload_limits import UploadBodyLimitMiddleware
from app.core.database import Base, engine
from app.core.logging import setup_logging
import app.models.models  # register models


@asynccontextmanager
async def lifespan(_: FastAPI):
    setup_logging()
    settings = get_settings()
    settings.upload_path.mkdir(parents=True, exist_ok=True)
    url = make_url(settings.database_url)
    if url.get_backend_name() == 'sqlite' and url.database and url.database != ':memory:':
        Path(url.database).parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    logger.info("RAG API started")
    yield


settings = get_settings()
app = FastAPI(title="Local RAG MVP", version="1.0.0", lifespan=lifespan)
app.add_middleware(UploadBodyLimitMiddleware, max_bytes=settings.upload_max_request_mb * 1024 * 1024)
app.add_middleware(ProtectedWriteMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])
register_model_errors(app)
app.include_router(router)
app.include_router(auth_router)
app.include_router(health_router)


@app.middleware('http')
async def response_security(request, call_next):
    request_id = uuid4().hex
    started = perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:
        logger.error('Unhandled failure request={} type={}', request_id, type(exc).__name__)
        response = JSONResponse(status_code=500, content={'detail': 'Dịch vụ gặp sự cố. Vui lòng thử lại. Mã tra cứu: ' + request_id})
    response.headers['X-Request-ID'] = request_id
    if request.url.path not in {'/health', '/ready', '/chat/models', '/auth/session'}:
        route = request.scope.get('route')
        logger.info('HTTP {} {} status={} duration_ms={:.0f} request={}', request.method,
                    getattr(route, 'path', 'unmatched'), response.status_code,
                    (perf_counter()-started)*1000, request_id)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    return response


@app.get("/health")
def health():
    return {"success": True, "message": "healthy", "data": {}}
