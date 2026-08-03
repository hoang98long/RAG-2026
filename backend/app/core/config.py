from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "sqlite:///./rag.db"
    ollama_base_url: str = "http://localhost:11434"
    llm_model: str = "qwen2.5:7b"
    embedding_model: str = "qwen3-embedding:0.6b"
    chroma_dir: str = "./chroma_data"
    upload_dir: str = "./storage/uploads"
    chunk_size: int = 1000
    chunk_overlap: int = 200
    top_k: int = 4
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    @property
    def upload_path(self) -> Path:
        return Path(self.upload_dir)


@lru_cache
def get_settings() -> Settings:
    return Settings()
