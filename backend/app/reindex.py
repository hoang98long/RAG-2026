"""Run from backend: python -m app.reindex. Stop the API while reindexing."""
from pathlib import Path
from sqlalchemy import select
from app.core.database import SessionLocal
from app.models.models import Document
from app.rag.chunking import load_chunks
from app.rag.vector_store import get_vector_store


def main() -> None:
    store = get_vector_store()
    with SessionLocal() as db:
        documents = db.scalars(select(Document).order_by(Document.id)).all()
        # Preflight before writing; source uploads and legacy indices stay intact.
        for document in documents:
            if not Path(document.filepath).is_file():
                raise FileNotFoundError(f"Missing source file: {document.filepath}")
        for document in documents:
            chunks = load_chunks(Path(document.filepath))
            if not chunks:
                raise ValueError(f"No readable text: {document.filename}")
            store.add(document.id, document.filename, chunks)
            print(f"Indexed {document.filename}: {len(chunks)} chunks")
    print(f"Ready: {store.collection.name} ({store.collection.count()} chunks)")


if __name__ == "__main__":
    main()
