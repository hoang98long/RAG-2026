"""General OpenAI conversation; no document, vector, SQL or RAG dependencies."""
from fastapi import HTTPException
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from app.schemas.schemas import DirectChatMessage
from app.services.model_provider import OpenAIChat

DIRECT_PROMPT = (
    'Bạn là trợ lý AI hữu ích, trả lời rõ ràng bằng tiếng Việt trừ khi người dùng yêu cầu ngôn ngữ khác. '
    'Đây là hội thoại trực tiếp, chỉ có nội dung người dùng nhập và các lượt trao đổi được gửi kèm. '
    'Bạn không có quyền đọc tài liệu, cơ sở dữ liệu hoặc tệp của ứng dụng, cũng không có công cụ duyệt web. '
    'Không khẳng định đã đọc tài liệu hoặc tìm kiếm trên web. Khi không chắc, nói rõ giới hạn hiểu biết.'
)


def direct_answer(messages: list[DirectChatMessage]) -> str:
    conversation = [SystemMessage(content=DIRECT_PROMPT)]
    conversation.extend(
        HumanMessage(content=item.content) if item.role == 'user' else AIMessage(content=item.content)
        for item in messages
    )
    provider = OpenAIChat(direct=True)
    try:
        response = provider.invoke(conversation)
    finally:
        provider.client.close()
    if not isinstance(response.content, str) or not response.content.strip():
        raise HTTPException(502, 'OpenAI chưa trả nội dung hợp lệ. Vui lòng thử lại.')
    return response.content
