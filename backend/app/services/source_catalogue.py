"""Scope-bound retrieval that rejects passages without a live source record/file."""
from pathlib import Path
from sqlalchemy import select
from app.core.config import get_settings
from app.models.models import Document
from app.rag.reranking import rerank
from app.rag.retrieval import select_sources


class CataloguedStore:
    def __init__(self, store, db, scope: str, *, document_ids: list[str] | None = None):
        self.store, self.db, self.scope = store, db, scope
        self.document_ids = None if document_ids is None else frozenset(document_ids)
        self.settings = get_settings()
        self.root = self.settings.scope_upload_path(scope).resolve()

    def _filter(self, items: list[dict]) -> list[dict]:
        candidates = [item for item in items if item.get('scope') == self.scope
                      and isinstance(item.get('document_id'), str) and item['document_id']
                      and (self.document_ids is None or item['document_id'] in self.document_ids)]
        identifiers = list(dict.fromkeys(item['document_id'] for item in candidates))
        available = {}
        # Bound SQL parameters independently of corpus size and query fan-out.
        for start in range(0, len(identifiers), 256):
            records = self.db.execute(select(Document.id, Document.filename, Document.filepath)
                .where(Document.id.in_(identifiers[start:start + 256])))
            for identifier, filename, filepath in records:
                try:
                    path = Path(filepath).resolve()
                    if path.is_relative_to(self.root) and path.is_file():
                        available[identifier] = filename
                except (OSError, ValueError):
                    continue
        return [item for item in candidates if item['document_id'] in available
                and item.get('document') == available[item['document_id']]]

    def candidates(self, query: str) -> list[dict]:
        return self._filter(self.store.candidates(query) if self.document_ids is None else
                            self.store.candidates(query, document_ids=sorted(self.document_ids)))

    def search(self, query: str, limit: int, *, use_rerank: bool = True, use_diversity: bool = True) -> list[dict]:
        return select_sources(rerank(query, self.candidates(query), enabled=use_rerank, diversify=use_diversity),
                              limit, self.settings.max_context_chars)

    def expand(self, source: dict, *, whole_section: bool, limit: int) -> tuple[list[dict], int]:
        if not self._filter([source]):
            return [], 0
        rows, total = self.store.expand(source, whole_section=whole_section, limit=limit)
        return self._filter(rows), total

    def related_section(self, source: dict, key: str, limit: int) -> tuple[list[dict], int]:
        if not self._filter([source]):
            return [], 0
        rows, total = self.store.related_section(source, key, limit)
        return self._filter(rows), total
