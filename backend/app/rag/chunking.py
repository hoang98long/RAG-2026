"""Extract page/section-aware chunks while preserving DOCX table row relationships."""
import re
import unicodedata
from pathlib import Path
from collections.abc import Iterator
from xml.etree import ElementTree as ET
from zipfile import ZipFile
from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from app.core.config import get_settings

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
HEADING = re.compile(r'^(?:Điều|Chương|Mục|Phần|Article|Chapter|Section)\s+(?:\d+|[IVXLC]+)(?:[\s.:]|$)', re.IGNORECASE)


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\x00", "").replace("\u200b", "").replace("\u00ad", "")
    text = re.sub(r"[^\S\n]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _xml_text(element) -> str:
    pieces = []
    for node in element.iter():
        if node.tag == W + 't':
            pieces.append(node.text or '')
        elif node.tag == W + 'tab':
            pieces.append(' ')
        elif node.tag in {W + 'br', W + 'cr'}:
            pieces.append('\n')
    return normalize_text(''.join(pieces))


def _docx_blocks(path: Path):
    section, header, buffer, buffered = '', '', [], 0
    window = max(get_settings().chunk_size * 4, 16384)
    with ZipFile(path) as archive, archive.open('word/document.xml') as stream:
        stack = []
        for event, element in ET.iterparse(stream, events=('start', 'end')):
            if event == 'start':
                stack.append(element)
                if element.tag == W + 'tbl' and len(stack) >= 2 and stack[-2].tag == W + 'body':
                    if buffer:
                        yield Document(page_content='\n\n'.join(buffer), metadata={'section': section})
                        buffer, buffered = [], 0
                    header = ''
                continue
            parent = stack[-2] if len(stack) >= 2 else None
            if element.tag == W + 'p' and parent is not None and parent.tag == W + 'body':
                text = _xml_text(element)
                if text:
                    style = element.find(f'{W}pPr/{W}pStyle')
                    style_id = style.get(W + 'val', '').lower() if style is not None else ''
                    outline = element.find(f'{W}pPr/{W}outlineLvl')
                    if style_id.startswith('heading') or style_id == 'title' or outline is not None or HEADING.match(text):
                        if buffer:
                            yield Document(page_content='\n\n'.join(buffer), metadata={'section': section})
                            buffer, buffered = [], 0
                        section = text[:220]
                    buffer.append(text)
                    buffered += len(text) + 2
                    if buffered >= window:
                        yield Document(page_content='\n\n'.join(buffer), metadata={'section': section})
                        buffer, buffered = [], 0
                parent.remove(element)
                element.clear()
            elif (element.tag == W + 'tr' and len(stack) >= 3 and
                  stack[-2].tag == W + 'tbl' and stack[-3].tag == W + 'body'):
                values = ['\n'.join(_xml_text(p) for p in cell.findall(W + 'p')) for cell in element.findall(W + 'tc')]
                line = ' | '.join(value.replace('\n', '; ') for value in values)
                if any(value.strip() for value in values):
                    flag = element.find(f'{W}trPr/{W}tblHeader')
                    if flag is not None and flag.get(W + 'val', 'true').lower() not in {'0', 'false', 'off'}:
                        header = line
                    content = f'{header}\n{line}' if header and line != header else line
                    yield Document(page_content=content, metadata={'section': section, 'table_header': header})
                parent.remove(element)
                element.clear()
            elif element.tag == W + 'tbl' and parent is not None and parent.tag == W + 'body':
                parent.remove(element)
                element.clear()
            stack.pop()
    if buffer:
        yield Document(page_content='\n\n'.join(buffer), metadata={'section': section})


def _pdf_blocks(path: Path) -> Iterator[Document]:
    pages = PyPDFLoader(str(path)).lazy_load()
    section = ''
    for page in pages:
        page.page_content = normalize_text(page.page_content)
        page.metadata['page'] = int(page.metadata.get('page', 0)) + 1
        lines, buffer = page.page_content.splitlines(keepends=True), []
        for line in lines:
            heading = line.strip()
            if len(heading) <= 220 and HEADING.match(heading):
                if buffer:
                    yield Document(page_content=''.join(buffer).strip(), metadata={**page.metadata, 'section': section})
                    buffer = []
                section = heading
            buffer.append(line)
        if buffer:
            yield Document(page_content=''.join(buffer).strip(), metadata={**page.metadata, 'section': section})


def iter_chunks(path: Path):
    settings = get_settings()
    blocks = _pdf_blocks(path) if path.suffix.lower() == '.pdf' else _docx_blocks(path)
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size, chunk_overlap=settings.chunk_overlap,
        separators=['\n\n', '\n', '. ', '! ', '? ', '; ', ' ', ''], add_start_index=True,
    )
    index = 0
    for block in blocks:
        if not block.page_content:
            continue
        for chunk in splitter.split_documents([block]):
            chunk.metadata['chunk_index'] = index
            index += 1
            yield chunk


def load_chunks(path: Path) -> list[Document]:
    """Convenience wrapper for small callers/tests; ingestion uses iter_chunks."""
    return list(iter_chunks(path))
