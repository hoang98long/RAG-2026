import hashlib
import json
from functools import lru_cache
from itertools import islice
from pathlib import Path
from threading import RLock
from typing import Iterable
import chromadb
from langchain_core.documents import Document
from langchain_ollama import OllamaEmbeddings
from app.core.config import get_settings
from app.rag.contextual import retrieval_text
from app.rag.lexical_store import LexicalStore
from app.rag.reranking import rerank
from app.rag.retrieval import fuse_rankings, select_sources


class VectorStore:
    def __init__(self):
        self.settings = get_settings()
        self.client = chromadb.PersistentClient(path=self.settings.chroma_dir)
        signature = json.dumps({'version': 4, 'embedding': self.settings.embedding_model,
                                'instruction': self.settings.embedding_query_instruction,
                                'chunk_size': self.settings.chunk_size,
                                'chunk_overlap': self.settings.chunk_overlap}, sort_keys=True)
        name = 'documents_v4_' + hashlib.sha256(signature.encode()).hexdigest()[:16]
        self.collection = self.client.get_or_create_collection(name, metadata={'hnsw:space': 'cosine'})
        self.lexical = LexicalStore(Path(self.settings.chroma_dir) / 'lexical' / f'{name}.sqlite3')
        self.embeddings = OllamaEmbeddings(model=self.settings.embedding_model, base_url=self.settings.ollama_base_url)
        self._lock = RLock()

    def rebuild_lexical(self):
        with self._lock:
            self.lexical.mark_dirty(True)
            self.lexical.clear()
            for offset in range(0, self.collection.count(), self.settings.index_page_size):
                batch = self.collection.get(limit=self.settings.index_page_size, offset=offset,
                                            include=['documents', 'metadatas'])
                self.lexical.upsert(batch['ids'], batch['documents'], batch['metadatas'])
            self.lexical.mark_dirty(False)

    def _ensure_lexical(self):
        if self.lexical.dirty() or self.lexical.count() != self.collection.count():
            self.rebuild_lexical()

    def add(self, document_id: str, filename: str, chunks: Iterable[Document]) -> int:
        with self._lock:
            self._ensure_lexical()
            self.lexical.mark_dirty(True)
            iterator, count = iter(chunks), 0
            while batch := list(islice(iterator, self.settings.embedding_batch_size)):
                texts = [chunk.page_content for chunk in batch]
                vectors = self.embeddings.embed_documents([retrieval_text(filename, chunk.page_content, chunk.metadata) for chunk in batch])
                metadata = []
                for index, chunk in enumerate(batch, start=count):
                    item = {'document_id': document_id, 'filename': filename, 'chunk_index': index,
                            'start_index': chunk.metadata.get('start_index', 0)}
                    for key in ('section', 'table_header', 'page'):
                        if key in chunk.metadata:
                            item[key] = chunk.metadata[key]
                    metadata.append(item)
                ids = [f'{document_id}-{index}' for index in range(count, count + len(batch))]
                self.collection.upsert(ids=ids, documents=texts, embeddings=vectors, metadatas=metadata)
                self.lexical.upsert(ids, texts, metadata)
                count += len(batch)
            if not count:
                raise ValueError("No readable chunks; existing document index was kept")
            # Predicate deletes avoid fetching every old chunk to trim a shorter source.
            self.collection.delete(where={'$and': [{'document_id': document_id}, {'chunk_index': {'$gte': count}}]})
            self.lexical.trim_document(document_id, count)
            self.lexical.mark_dirty(False)
            return count

    def search(self, query: str, limit: int, *, use_rerank: bool = True) -> list[dict]:
        with self._lock:
            count = self.collection.count()
            if not count or not query.strip():
                return []
            self._ensure_lexical()
            instruction = self.settings.embedding_query_instruction
            embedding_query = (f'Instruct: {instruction}\nQuery: {query}'
                               if instruction and self.settings.embedding_model.startswith('qwen3-embedding') else query)
            pool = min(self.settings.retrieval_candidates, count)
            result = self.collection.query(query_embeddings=[self.embeddings.embed_query(embedding_query)], n_results=pool,
                                           include=['distances'])
            dense_ids = result['ids'][0]
            similarities = dict(zip(dense_ids, (1 - distance for distance in result['distances'][0])))
            dense_ids = [identifier for identifier in dense_ids if similarities[identifier] >= self.settings.min_similarity]
            lexical_ids = self.lexical.search(query, pool)
            ranking = fuse_rankings(dense_ids, lexical_ids)
            # Only candidate text is read; the corpus is never materialized for a query.
            by_id = self.lexical.get([identifier for identifier, _ in ranking])
            candidates = []
            for identifier, score in ranking:
                text, meta = by_id[identifier]
                candidates.append({'content': text, 'document': meta['filename'], 'document_id': meta['document_id'],
                                   'chunk_index': meta['chunk_index'], 'page': meta.get('page'),
                                   'section': meta.get('section', ''), 'table_header': meta.get('table_header', ''),
                                   'score': score, 'similarity': similarities.get(identifier)})
        return select_sources(rerank(query, candidates, enabled=use_rerank), limit, self.settings.max_context_chars)

    def document_page(self, document_id: str, **kwargs) -> dict:
        with self._lock:
            self._ensure_lexical()
            return self.lexical.document_page(document_id, **kwargs)

    def document_chunks(self, document_id: str) -> list[dict]:
        return self.document_page(document_id, limit=self.settings.index_page_size)['chunks']

    def delete_document(self, document_id: str) -> None:
        with self._lock:
            for collection in self.client.list_collections():
                name = collection if isinstance(collection, str) else collection.name
                if name == 'documents' or name.startswith(('documents_v2_', 'documents_v3_', 'documents_v4_')):
                    self.client.get_collection(name).delete(where={'document_id': document_id})
            for path in (Path(self.settings.chroma_dir) / 'lexical').glob('documents_v*.sqlite3'):
                LexicalStore(path).delete_document(document_id)


@lru_cache
def get_vector_store() -> VectorStore:
    return VectorStore()
