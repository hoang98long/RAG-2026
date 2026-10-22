from functools import lru_cache
from pathlib import Path
from typing import Literal
from pydantic import Field, SecretStr, model_validator
from sqlalchemy.engine import make_url
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)
    database_url: str = "sqlite:///./rag.db"
    ollama_base_url: str = "http://localhost:11434"
    llm_model: str = "qwen2.5:7b"
    embedding_model: str = "qwen3-embedding:0.6b"
    chroma_dir: str = "./chroma_data"
    upload_dir: str = "./storage/uploads"
    public_database_url: str = "sqlite:///./storage/public/public.db"
    public_chroma_dir: str = "./public_chroma_data"
    public_upload_dir: str = "./storage/public/uploads"
    internal_access_token: SecretStr = SecretStr("")
    session_max_age: int = Field(default=14400, ge=300, le=86400)
    session_cookie_secure: bool = False
    public_chat_rate_limit: int = Field(default=20, ge=1, le=1000)
    public_chat_max_concurrent: int = Field(default=2, ge=1, le=16)
    openai_api_key: SecretStr = SecretStr("")
    openai_model: str = "gpt-4.1-mini"
    openai_chat_model: str = "gpt-6-luna"
    openai_timeout: float = Field(default=90, gt=0)
    llm_timeout: float = Field(default=180, gt=0)
    embedding_timeout: float = Field(default=120, gt=0)
    review_batch_size: int = Field(default=6, ge=1, le=12)
    report_context_chars: int = Field(default=10000, ge=2000, le=24000)
    report_section_chunks: int = Field(default=8, ge=2, le=24)
    report_rerank_candidates: int = Field(default=12, ge=1, le=48)
    report_max_seconds: float = Field(default=420, gt=0, le=1800)
    query_expansion: bool = True
    grounding_verification: bool = True
    evidence_max_chunks: int = Field(default=80, ge=6, le=200)
    exhaustive_context_chars: int = Field(default=32000, ge=2000, le=100000)
    exhaustive_num_predict: int = Field(default=4096, ge=512)
    neighbor_chunks: int = Field(default=1, ge=0, le=3)
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
    rerank_diversity_lambda: float = Field(default=0.75, ge=0, le=1, allow_inf_nan=False)
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
        token = self.internal_access_token.get_secret_value().strip()
        if token and (len(token) < 32 or len(token) > 512):
            raise ValueError('INTERNAL_ACCESS_TOKEN must contain 32 to 512 characters')
        if '*' in {origin.strip() for origin in self.cors_origins.split(',')}:
            raise ValueError('CORS_ORIGINS must list explicit trusted origins')
        private_db, public_db = make_url(self.database_url), make_url(self.public_database_url)
        if public_db.get_backend_name() != 'sqlite' or not public_db.database or public_db.database == ':memory:':
            raise ValueError('PUBLIC_DATABASE_URL must be a persistent SQLite database')
        if (private_db == public_db or (private_db.get_backend_name() == 'sqlite' and private_db.database
                and Path(private_db.database).resolve() == Path(public_db.database).resolve())):
            raise ValueError('Private and public metadata databases must be distinct')
        for private in (self.chroma_dir, self.upload_dir):
            for public in (self.public_chroma_dir, self.public_upload_dir):
                a, b = Path(private).resolve(), Path(public).resolve()
                if a == b or a.is_relative_to(b) or b.is_relative_to(a):
                    raise ValueError('Private and public storage directories must not overlap')
        if self.upload_max_request_mb <= self.upload_max_file_mb:
            raise ValueError("UPLOAD_MAX_REQUEST_MB must exceed UPLOAD_MAX_FILE_MB for multipart overhead")
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("CHUNK_OVERLAP must be smaller than CHUNK_SIZE")
        if self.retrieval_candidates < self.top_k:
            raise ValueError("RETRIEVAL_CANDIDATES must be >= TOP_K")
        if self.rerank_candidates < self.top_k:
            raise ValueError("RERANK_CANDIDATES must be >= TOP_K")
        if self.exhaustive_num_predict >= self.llm_num_ctx:
            raise ValueError("EXHAUSTIVE_NUM_PREDICT must be smaller than LLM_NUM_CTX")
        if self.llm_num_predict >= self.llm_num_ctx:
            raise ValueError("LLM_NUM_PREDICT must be smaller than LLM_NUM_CTX")
        if self.max_context_chars < self.chunk_size + 400:
            raise ValueError("MAX_CONTEXT_CHARS must be >= CHUNK_SIZE + 400")
        return self

    def scope_upload_path(self, scope: str) -> Path:
        if scope not in {'private', 'public'}:
            raise ValueError('Invalid document scope')
        return Path(self.public_upload_dir if scope == 'public' else self.upload_dir)

    @property
    def upload_path(self) -> Path:
        return Path(self.upload_dir)


@lru_cache
def get_settings() -> Settings:
    return Settings()
