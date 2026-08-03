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


class ReportRequest(BaseModel):
    template: str = Field(pattern="^(technical|meeting|research)$")
    title: str = Field(min_length=1)
    instructions: str = ""


class DashboardStats(BaseModel):
    documents: int
    chats: int
    reports: int
