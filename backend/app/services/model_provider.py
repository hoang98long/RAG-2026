"""Server-side OpenAI routing without tools, stored conversation IDs or private-store access."""
from fastapi import HTTPException
from langchain_core.messages import AIMessage
from app.core.config import get_settings

LOCAL_MODELS = {'qwen2.5:7b', 'llama3.1:70b'}


def validate_selection(model: str, scope: str):
    if scope not in {'private', 'public', 'all'}:
        raise HTTPException(403, 'Phạm vi tài liệu không hợp lệ')
    if model not in LOCAL_MODELS | {'openai'} or scope not in {'private', 'public', 'all'}:
        raise HTTPException(422, 'Lựa chọn mô hình hoặc kho tài liệu không hợp lệ')
    if model == 'openai':
        if scope != 'public':
            raise HTTPException(403, 'OpenAI chỉ được sử dụng kho tài liệu public')
        if not get_settings().openai_api_key.get_secret_value().strip():
            raise HTTPException(503, 'Chưa cấu hình OPENAI_API_KEY trên backend')


def assert_public_sources(sources: list[dict]):
    if any(source.get('scope') != 'public' for source in sources):
        raise HTTPException(403, 'Đã chặn gửi nguồn không thuộc kho public tới OpenAI')


def provider_error(exc: Exception) -> HTTPException:
    """Return safe, actionable errors without provider payloads or credentials."""
    from openai import APIStatusError, APITimeoutError, APIConnectionError
    if isinstance(exc, APIStatusError):
        code = exc.body.get('code') if isinstance(exc.body, dict) else None
        if code == 'credit_balance_exhausted':
            return HTTPException(503, 'OpenAI đã hết credit API. Quản trị viên cần bổ sung credit trước khi sử dụng.')
        if code in {'insufficient_quota', 'organization_spend_limit_exceeded', 'project_spend_limit_exceeded',
                    'organization_usage_limit_exceeded'}:
            return HTTPException(503, 'OpenAI đã chạm hạn mức API. Quản trị viên cần kiểm tra billing và giới hạn sử dụng.')
        if exc.status_code == 429:
            return HTTPException(429, 'OpenAI đang giới hạn số yêu cầu. Vui lòng chờ rồi thử lại.', headers={'Retry-After': '10'})
        if exc.status_code in {401, 403}:
            return HTTPException(503, 'OpenAI key hoặc quyền truy cập mô hình chưa hợp lệ. Vui lòng liên hệ quản trị viên.')
    if isinstance(exc, APITimeoutError):
        return HTTPException(504, 'OpenAI phản hồi quá lâu. Vui lòng thử lại.')
    if isinstance(exc, APIConnectionError):
        return HTTPException(503, 'Không kết nối được OpenAI. Vui lòng kiểm tra kết nối mạng của máy chủ.')
    return HTTPException(502, 'Không thể gọi OpenAI. Kiểm tra key, quyền model, hạn mức và kết nối.')


class OpenAIChat:
    """Minimal LangChain-compatible adapter to the stateless Responses API."""
    def __init__(self):
        settings = get_settings()
        validate_selection('openai', 'public')
        from openai import OpenAI
        self.client = OpenAI(api_key=settings.openai_api_key.get_secret_value(), timeout=settings.openai_timeout, max_retries=1)
        self.model = settings.openai_model
        self.max_output_tokens = settings.llm_num_predict

    @staticmethod
    def _input(messages):
        roles = {'system': 'system', 'human': 'user', 'ai': 'assistant'}
        return [{'role': roles[message.type], 'content': message.content} for message in messages]

    def invoke(self, messages):
        try:
            result = self.client.responses.create(model=self.model, input=self._input(messages),
                                                   max_output_tokens=self.max_output_tokens, store=False)
            if result.status != 'completed':
                raise HTTPException(502, 'OpenAI chưa hoàn tất câu trả lời; hãy thu hẹp câu hỏi hoặc tăng giới hạn đầu ra')
            return AIMessage(content=result.output_text)
        except HTTPException:
            raise
        except Exception as exc:
            # Do not expose provider payloads, prompts or keys in HTTP errors.
            raise provider_error(exc) from exc

    def with_structured_output(self, schema, **kwargs):
        owner = self
        class Structured:
            def invoke(self, messages):
                try:
                    result = owner.client.responses.parse(model=owner.model, input=owner._input(messages),
                        text_format=schema, max_output_tokens=owner.max_output_tokens, store=False)
                    if result.status != 'completed' or result.output_parsed is None:
                        raise ValueError('Missing structured response')
                    return result.output_parsed
                except Exception as exc:
                    raise provider_error(exc) from exc
        return Structured()
