import hashlib
import json
from functools import lru_cache
from threading import RLock
import chromadb
from langchain_core.documents import Document
from langchain_ollama import OllamaEmbeddings
from app.core.config import get_settings
from app.rag.retrieval import BM25Index, fuse_rankings, select_sources


class VectorStore:
    def __init__(self):
        self.settings = get_settings()
        self.client = chromadb.PersistentClient(path=self.settings.chroma_dir)
        signature = json.dumps({"version": 2, "embedding": self.settings.embedding_model,
                                "instruction": self.settings.embedding_query_instruction,
                                "chunk_size": self.settings.chunk_size,
                                "chunk_overlap": self.settings.chunk_overlap}, sort_keys=True)
        name = "documents_v2_" + hashlib.sha256(signature.encode()).hexdigest()[:16]
        self.collection = self.client.get_or_create_collection(name, metadata={"hnsw:space": "cosine"})
        self.embeddings = OllamaEmbeddings(model=self.settings.embedding_model,
                                          base_url=self.settings.ollama_base_url)
        self._lock = RLock()
        self._corpus = None
        self._bm25 = None

    def add(self, document_id: str, filename: str, chunks: list[Document]) -> None:
        batch_size = self.settings.embedding_batch_size
        with self._lock:
            try:
                for start in range(0, len(chunks), batch_size):
                    batch = chunks[start:start + batch_size]
                    texts = [chunk.page_content for chunk in batch]
                    vectors = self.embeddings.embed_documents(texts)
                    metadata = []
                    for index, chunk in enumerate(batch, start=start):
                        item = {"document_id": document_id, "filename": filename, "chunk_index": index,
                                "start_index": chunk.metadata.get("start_index", 0)}
                        if "page" in chunk.metadata:
                            item["page"] = chunk.metadata["page"]
                        metadata.append(item)
                    self.collection.upsert(ids=[f"{document_id}-{i}" for i in range(start, start + len(batch))],
                                           documents=texts, embeddings=vectors, metadatas=metadata)
                old = self.collection.get(where={"document_id": document_id}, include=["metadatas"])
                stale = [identifier for identifier, meta in zip(old["ids"], old["metadatas"])
                         if meta["chunk_index"] >= len(chunks)]
                if stale:
                    self.collection.delete(ids=stale)
            finally:
                self._corpus = None

    def search(self, query: str, limit: int) -> list[dict]:
        with self._lock:
            count = self.collection.count()
            if not count or not query.strip():
                return []
            if self._corpus is None or len(self._corpus["ids"]) != count:
                self._corpus = self.collection.get(include=["documents", "metadatas"])
                self._bm25 = BM25Index(self._corpus["documents"])
            corpus = self._corpus
            instruction = self.settings.embedding_query_instruction
            embedding_query = (f"Instruct: {instruction}\nQuery: {query}"
                               if instruction and self.settings.embedding_model.startswith("qwen3-embedding") else query)
            pool = min(self.settings.retrieval_candidates, count)
            result = self.collection.query(query_embeddings=[self.embeddings.embed_query(embedding_query)],
                                           n_results=pool, include=["documents", "metadatas", "distances"])
            dense_ids = result["ids"][0]
            similarities = dict(zip(dense_ids, (1 - distance for distance in result["distances"][0])))
            lexical_ids = [corpus["ids"][i] for i in self._bm25.search(query, pool)]
            # The cosine threshold does not reject keyword matches.
            dense_ids = [identifier for identifier in dense_ids
                         if similarities[identifier] >= self.settings.min_similarity]
            by_id = {identifier: (text, meta) for identifier, text, meta in
                     zip(corpus["ids"], corpus["documents"], corpus["metadatas"])}
            candidates = []
            for identifier, score in fuse_rankings(dense_ids, lexical_ids):
                text, meta = by_id[identifier]
                candidates.append({"content": text, "document": meta["filename"],
                                   "document_id": meta["document_id"], "chunk_index": meta["chunk_index"],
                                   "page": meta.get("page"), "score": score,
                                   "similarity": similarities.get(identifier)})
            return select_sources(candidates, limit, self.settings.max_context_chars)

    def delete_document(self, document_id: str) -> None:
        with self._lock:
            for collection in self.client.list_collections():
                name = collection if isinstance(collection, str) else collection.name
                if name == "documents" or name.startswith("documents_v2_"):
                    self.client.get_collection(name).delete(where={"document_id": document_id})
            self._corpus = None


@lru_cache
def get_vector_store() -> VectorStore:
    return VectorStore()
