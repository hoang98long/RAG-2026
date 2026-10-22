from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field, field_validator


class DocumentOut(BaseModel):
    id: str
    filename: str
    upload_time: datetime
    model_config = {"from_attributes": True}


class ChatRequest(BaseModel):
    model_config = {'extra': 'forbid'}
    question: str = Field(min_length=1, max_length=12000)
    model: Literal['qwen2.5:7b', 'llama3.1:70b', 'openai'] = 'qwen2.5:7b'
    scope: Literal['private', 'public', 'all'] = 'private'

    @field_validator('question')
    @classmethod
    def trim_question(cls, value):
        if not value.strip():
            raise ValueError('Question must contain text')
        return value.strip()



class DirectChatMessage(BaseModel):
    model_config = {'extra': 'forbid'}
    role: Literal['user', 'assistant']
    content: str = Field(min_length=1, max_length=12000)

    @field_validator('content')
    @classmethod
    def meaningful_content(cls, value):
        if not value.strip():
            raise ValueError('Message must contain text')
        return value.strip()


class DirectChatRequest(BaseModel):
    model_config = {'extra': 'forbid'}
    messages: list[DirectChatMessage] = Field(min_length=1, max_length=21)

    @field_validator('messages')
    @classmethod
    def bounded_conversation(cls, messages):
        if len(messages) % 2 != 1 or any(
                item.role != ('user' if index % 2 == 0 else 'assistant')
                for index, item in enumerate(messages)):
            raise ValueError('Conversation must alternate user/assistant and end with a user message')
        if sum(len(item.content.encode('utf-8')) for item in messages) > 48000:
            raise ValueError('Conversation exceeds the context size limit')
        return messages


class SourceChunk(BaseModel):
    scope: Literal['private', 'public'] | None = None
    index_version: str | None = None
    digest: str | None = None
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
    model_config = {'extra': 'forbid'}
    template: str = Field(pattern="^(technical|meeting|research)$")
    title: str = Field(min_length=1, max_length=500)
    instructions: str = Field(default="", max_length=12000)
    model: Literal['qwen2.5:7b', 'llama3.1:70b'] = 'qwen2.5:7b'
    document_ids: list[str] | None = Field(default=None, min_length=1, max_length=20)
    sections: list[str] | None = Field(default=None, min_length=1, max_length=4)

    @field_validator('title')
    @classmethod
    def meaningful_title(cls, value):
        if not value.strip():
            raise ValueError('Title must contain text')
        return value.strip()

    @field_validator('sections', 'document_ids')
    @classmethod
    def bounded_items(cls, values, info):
        if values is None:
            return None
        limit = 120 if info.field_name == 'sections' else 36
        cleaned = [item.strip() for item in values]
        if any(not item or len(item) > limit or '\n' in item or '\r' in item for item in cleaned):
            raise ValueError('Invalid report selection')
        if len(set(cleaned)) != len(cleaned):
            raise ValueError('Duplicate report selection')
        return cleaned



class DashboardStats(BaseModel):
    documents: int
    chats: int
    reports: int
