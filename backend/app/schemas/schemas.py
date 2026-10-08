from datetime import datetime
from pydantic import BaseModel, Field


class DocumentOut(BaseModel):
    id: str
    filename: str
    upload_time: datetime
    model_config = {"from_attributes": True}


class ChatRequest(BaseModel):
    question: str = Field(min_length=1)


class SourceChunk(BaseModel):
    document: str
    content: str
    source_id: str | None = None
    document_id: str | None = None
    page: int | None = None
    chunk_index: int | None = None
    score: float | None = None
    similarity: float | None = None
    section: str = ""
    table_header: str = ""
    rerank_score: float | None = None
    rerank_method: str | None = None


class ReportRequest(BaseModel):
    template: str = Field(pattern="^(technical|meeting|research)$")
    title: str = Field(min_length=1)
    instructions: str = ""


class DashboardStats(BaseModel):
    documents: int
    chats: int
    reports: int
