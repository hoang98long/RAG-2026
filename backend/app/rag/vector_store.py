from functools import lru_cache
import chromadb
from langchain_ollama import OllamaEmbeddings
from app.core.config import get_settings


class VectorStore:
    def __init__(self):
        settings = get_settings()
        self.client = chromadb.PersistentClient(path=settings.chroma_dir)
        self.collection = self.client.get_or_create_collection("documents")
        self.embeddings = OllamaEmbeddings(model=settings.embedding_model, base_url=settings.ollama_base_url)

    def add(self, document_id: str, filename: str, chunks: list[str]) -> None:
        embeddings = self.embeddings.embed_documents(chunks)
        ids = [f"{document_id}-{index}" for index in range(len(chunks))]
        self.collection.add(ids=ids, documents=chunks, embeddings=embeddings,
                            metadatas=[{"document_id": document_id, "filename": filename}] * len(chunks))

    def search(self, query: str, limit: int) -> list[dict]:
        result = self.collection.query(query_embeddings=[self.embeddings.embed_query(query)], n_results=limit,
                                       include=["documents", "metadatas"])
        docs = result.get("documents", [[]])[0]
        meta = result.get("metadatas", [[]])[0]
        return [{"content": text, "document": item.get("filename", "Không rõ")} for text, item in zip(docs, meta)]

    def delete_document(self, document_id: str) -> None:
        self.collection.delete(where={"document_id": document_id})


@lru_cache
def get_vector_store() -> VectorStore:
    return VectorStore()
