"""Disk-backed BM25 index and bounded source lookup (one SQLite file per collection)."""
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from app.rag.contextual import retrieval_text
from app.rag.retrieval import tokenize


class LexicalStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript('''
CREATE TABLE IF NOT EXISTS chunks (
    rowid INTEGER PRIMARY KEY, chunk_id TEXT NOT NULL UNIQUE,
    document_id TEXT NOT NULL, chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL, metadata TEXT NOT NULL, search_text TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS chunks_document ON chunks(document_id, chunk_index);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    search_text, content='chunks', content_rowid='rowid', tokenize='unicode61 remove_diacritics 0'
);
CREATE TRIGGER IF NOT EXISTS chunks_insert AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, search_text) VALUES (new.rowid, new.search_text);
END;
CREATE TRIGGER IF NOT EXISTS chunks_delete AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, search_text) VALUES ('delete', old.rowid, old.search_text);
END;
CREATE TRIGGER IF NOT EXISTS chunks_update AFTER UPDATE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, search_text) VALUES ('delete', old.rowid, old.search_text);
    INSERT INTO chunks_fts(rowid, search_text) VALUES (new.rowid, new.search_text);
END;
CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value INTEGER NOT NULL);
INSERT OR IGNORE INTO state VALUES ('dirty', 0);
''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def count(self) -> int:
        with self.connect() as db:
            return db.execute('SELECT count(*) FROM chunks').fetchone()[0]

    def dirty(self) -> bool:
        with self.connect() as db:
            return bool(db.execute("SELECT value FROM state WHERE key='dirty'").fetchone()[0])

    def mark_dirty(self, value: bool):
        with self.connect() as db:
            db.execute("UPDATE state SET value=? WHERE key='dirty'", (int(value),))

    def upsert(self, ids: list[str], documents: list[str], metadatas: list[dict]):
        rows = [(identifier, meta['document_id'], meta['chunk_index'], text,
                 json.dumps(meta, ensure_ascii=False), retrieval_text(meta['filename'], text, meta))
                for identifier, text, meta in zip(ids, documents, metadatas)]
        with self.connect() as db:
            db.executemany('''INSERT INTO chunks(chunk_id, document_id, chunk_index, content, metadata, search_text)
VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(chunk_id) DO UPDATE SET document_id=excluded.document_id,
chunk_index=excluded.chunk_index, content=excluded.content, metadata=excluded.metadata, search_text=excluded.search_text''', rows)

    def search(self, query: str, limit: int) -> list[str]:
        # Quote tokens rather than accepting raw FTS syntax from the question.
        terms = list(dict.fromkeys(tokenize(query)))[:128]
        if not terms:
            return []
        expression = ' OR '.join('"' + term.replace('"', '""') + '"' for term in terms)
        with self.connect() as db:
            return [row[0] for row in db.execute('''SELECT chunks.chunk_id FROM chunks_fts
JOIN chunks ON chunks.rowid=chunks_fts.rowid WHERE chunks_fts MATCH ?
ORDER BY bm25(chunks_fts), chunks.chunk_id LIMIT ?''', (expression, limit))]

    def get(self, ids: list[str]) -> dict[str, tuple[str, dict]]:
        if not ids:
            return {}
        with self.connect() as db:
            rows = db.execute('SELECT chunk_id, content, metadata FROM chunks WHERE chunk_id IN ('
                              + ','.join('?' for _ in ids) + ')', ids)
            return {row['chunk_id']: (row['content'], json.loads(row['metadata'])) for row in rows}

    def trim_document(self, document_id: str, count: int):
        with self.connect() as db:
            db.execute('DELETE FROM chunks WHERE document_id=? AND chunk_index>=?', (document_id, count))

    def delete_document(self, document_id: str):
        self.trim_document(document_id, 0)

    def clear(self):
        with self.connect() as db:
            db.execute('DELETE FROM chunks')

    def document_page(self, document_id: str, offset: int = 0, limit: int = 50,
                      chunk_index: int | None = None, page: int | None = None) -> dict:
        with self.connect() as db:
            total = db.execute('SELECT count(*) FROM chunks WHERE document_id=?', (document_id,)).fetchone()[0]
            target = chunk_index
            if target is None and page is not None:
                # Only this document is examined; JSON metadata retains page provenance.
                row = db.execute("SELECT min(chunk_index) FROM chunks WHERE document_id=? AND json_extract(metadata, '$.page')=?",
                                 (document_id, page)).fetchone()
                target = row[0]
            found = False if page is not None and target is None else None
            if target is not None:
                found = db.execute('SELECT 1 FROM chunks WHERE document_id=? AND chunk_index=?', (document_id, target)).fetchone() is not None
                offset = (target // limit) * limit
            rows = db.execute('SELECT content, metadata, chunk_index FROM chunks WHERE document_id=? AND chunk_index>=? '
                              'ORDER BY chunk_index LIMIT ?', (document_id, offset, limit)).fetchall()
            chunks = [{'content': row['content'], 'chunk_index': row['chunk_index'],
                       'page': json.loads(row['metadata']).get('page')} for row in rows]
            return {'chunks': chunks, 'total': total, 'offset': offset, 'limit': limit, 'target_found': found}
