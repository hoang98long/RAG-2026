from pathlib import Path
from langchain_ollama import ChatOllama
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.models.models import ChatHistory, ReportHistory
from app.rag.vector_store import get_vector_store


def _prompt(name: str, **values: str) -> str:
    return (Path(__file__).parent.parent / "prompts" / f"{name}.txt").read_text(encoding="utf-8").format(**values)


def _context(sources: list[dict]) -> str:
    return "\n\n".join(f"[{item['document']}]\n{item['content']}" for item in sources)


def _llm() -> ChatOllama:
    settings = get_settings()
    return ChatOllama(model=settings.llm_model, base_url=settings.ollama_base_url, temperature=0)


def answer(question: str, db: Session) -> tuple[str, list[dict], bool]:
    settings = get_settings()
    sources = get_vector_store().search(question, settings.top_k)
    if not sources:
        text = "Chưa có nội dung tài liệu phù hợp. Hãy tải tài liệu lên trước."
    else:
        text = _llm().invoke(_prompt("chat", context=_context(sources), question=question)).content
    db.add(ChatHistory(question=question, answer=text))
    db.commit()
    return text, sources, False


def generate_report(template: str, title: str, instructions: str, db: Session) -> tuple[str, list[dict]]:
    settings = get_settings()
    sources = get_vector_store().search(f"{title} {instructions}", settings.top_k)
    if not sources:
        text = "# Không thể tạo báo cáo\n\nChưa có tài liệu để làm nguồn tham chiếu."
    else:
        text = _llm().invoke(_prompt(template, title=title, instructions=instructions, context=_context(sources))).content
    db.add(ReportHistory(title=title, template=template, content=text))
    db.commit()
    return text, sources
