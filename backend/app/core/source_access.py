"""Fail-closed passage scope checks, independent of model instructions."""
from fastapi import HTTPException


def assert_source_scope(sources: list[dict], allowed: set[str], document_id: str | None = None):
    if not allowed or not allowed.issubset({'private','public'}):
        raise HTTPException(403, 'Phạm vi tài liệu không hợp lệ')
    if any(item.get('scope') not in allowed or
           (document_id is not None and item.get('document_id') != document_id) for item in sources):
        raise HTTPException(403, 'Đã chặn nguồn nằm ngoài phạm vi tài liệu được phép')
