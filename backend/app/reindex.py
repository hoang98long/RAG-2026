"""Run from backend while the API is stopped. No full-file chunk lists in memory."""
import argparse
from pathlib import Path
from sqlalchemy import select
from app.core.database import SessionLocal
from app.models.models import Document
from app.rag.chunking import iter_chunks
from app.rag.vector_store import get_vector_store


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lexical-only', action='store_true', help='Rebuild FTS from current vectors without calling Ollama')
    args = parser.parse_args()
    store = get_vector_store()
    if args.lexical_only:
        store.rebuild_lexical()
        print(f'Lexical index ready: {store.lexical.count()} chunks')
        return
    with SessionLocal() as db:
        missing = db.scalars(select(Document).order_by(Document.id).execution_options(yield_per=100))
        for document in missing:
            if not Path(document.filepath).is_file():
                raise FileNotFoundError(f'Missing source file: {document.filepath}')
        documents = db.scalars(select(Document).order_by(Document.id).execution_options(yield_per=100))
        for document in documents:
            chunks = iter_chunks(Path(document.filepath))
            try:
                count = store.add(document.id, document.filename, chunks)
            finally:
                chunks.close()
            if not count:
                raise ValueError(f'No readable text: {document.filename}')
            print(f'Indexed {document.filename}: {count} chunks')
    print(f'Ready: {store.collection.name} ({store.collection.count()} chunks)')


if __name__ == '__main__':
    main()
