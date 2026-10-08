"""Page-aware extraction. Chunk sizes are Unicode characters, not tokens."""
import re
import unicodedata
from pathlib import Path
from langchain_community.document_loaders import Docx2txtLoader, PyPDFLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from app.core.config import get_settings


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\x00", "").replace("\u200b", "").replace("\u00ad", "")
    text = re.sub(r"[^\S\n]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def load_chunks(path: Path) -> list[Document]:
    settings = get_settings()
    loader = PyPDFLoader(str(path)) if path.suffix.lower() == ".pdf" else Docx2txtLoader(str(path))
    pages = loader.load()
    for page in pages:
        page.page_content = normalize_text(page.page_content)
        if "page" in page.metadata:
            page.metadata["page"] = int(page.metadata["page"]) + 1
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size, chunk_overlap=settings.chunk_overlap,
        separators=["\n\n", "\n", ". ", "! ", "? ", "; ", " ", ""],
        add_start_index=True,
    )
    chunks = splitter.split_documents([page for page in pages if page.page_content])
    for index, chunk in enumerate(chunks):
        chunk.metadata["chunk_index"] = index
    return chunks
