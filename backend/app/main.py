from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from app.api.routes import router
from app.core.config import get_settings
from app.core.upload_limits import UploadBodyLimitMiddleware
from app.core.database import Base, engine
from app.core.logging import setup_logging
import app.models.models  # register models


@asynccontextmanager
async def lifespan(_: FastAPI):
    setup_logging()
    settings = get_settings()
    settings.upload_path.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    logger.info("RAG API started")
    yield


settings = get_settings()
app = FastAPI(title="Local RAG MVP", version="1.0.0", lifespan=lifespan)
app.add_middleware(UploadBodyLimitMiddleware, max_bytes=settings.upload_max_request_mb * 1024 * 1024)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins.split(","), allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(router)


@app.get("/health")
def health():
    return {"success": True, "message": "healthy", "data": {}}
