from functools import lru_cache
from pathlib import Path
from typing import Literal
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "sqlite:///./rag.db"
    ollama_base_url: str = "http://localhost:11434"
    llm_model: str = "qwen2.5:7b"
    embedding_model: str = "qwen3-embedding:0.6b"
    chroma_dir: str = "./chroma_data"
    upload_dir: str = "./storage/uploads"
    chunk_size: int = Field(default=1600, ge=200)
    chunk_overlap: int = Field(default=240, ge=0)
    top_k: int = Field(default=6, ge=1)
    retrieval_candidates: int = Field(default=48, ge=1)
    min_similarity: float = Field(default=0.0, ge=-1, le=1)
    max_context_chars: int = Field(default=14000, ge=200)
    llm_num_ctx: int = Field(default=16384, ge=2048)
    llm_num_predict: int = Field(default=2048, ge=128)
    embedding_batch_size: int = Field(default=32, ge=1, le=256)
    embedding_query_instruction: str = "Given a question, retrieve relevant document passages that answer the question."
    rerank_backend: Literal["off", "ollama", "cross_encoder"] = "ollama"
    rerank_model: str = ""
    rerank_candidates: int = Field(default=32, ge=1)
    rerank_batch_size: int = Field(default=6, ge=1, le=16)
    rerank_min_grade: int = Field(default=2, ge=0, le=3)
    rerank_timeout: float = Field(default=120, gt=0)
    cross_encoder_model: str = "BAAI/bge-reranker-v2-m3"
    cross_encoder_device: str = "cpu"
    cross_encoder_max_length: int = Field(default=1024, ge=128, le=8192)
    cross_encoder_min_score: float | None = Field(default=None, allow_inf_nan=False)
    citation_repair: bool = True
    index_page_size: int = Field(default=500, ge=1, le=2000)
    upload_max_file_mb: int = Field(default=200, ge=1)
    upload_max_request_mb: int = Field(default=512, ge=1)
    upload_max_files: int = Field(default=20, ge=1, le=1000)
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    @model_validator(mode="after")
    def validate_rag(self):
        if self.upload_max_request_mb <= self.upload_max_file_mb:
            raise ValueError("UPLOAD_MAX_REQUEST_MB must exceed UPLOAD_MAX_FILE_MB for multipart overhead")
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("CHUNK_OVERLAP must be smaller than CHUNK_SIZE")
        if self.retrieval_candidates < self.top_k:
            raise ValueError("RETRIEVAL_CANDIDATES must be >= TOP_K")
        if self.rerank_candidates < self.top_k:
            raise ValueError("RERANK_CANDIDATES must be >= TOP_K")
        if self.llm_num_predict >= self.llm_num_ctx:
            raise ValueError("LLM_NUM_PREDICT must be smaller than LLM_NUM_CTX")
        if self.max_context_chars < self.chunk_size + 400:
            raise ValueError("MAX_CONTEXT_CHARS must be >= CHUNK_SIZE + 400")
        return self

    @property
    def upload_path(self) -> Path:
        return Path(self.upload_dir)


@lru_cache
def get_settings() -> Settings:
    return Settings()
