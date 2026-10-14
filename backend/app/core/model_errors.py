import httpx
from fastapi.responses import JSONResponse
from ollama import ResponseError


def register_model_errors(app):
    async def timeout_handler(request, exc):
        return JSONResponse(status_code=504, content={'detail': 'Dịch vụ mô hình phản hồi quá lâu. Hãy thử câu hỏi ngắn hơn hoặc kiểm tra tài nguyên máy.'})
    async def connection_handler(request, exc):
        return JSONResponse(status_code=503, content={'detail': 'Không kết nối được dịch vụ mô hình. Hãy kiểm tra Ollama và dịch vụ embedding.'})
    async def model_handler(request, exc):
        missing = exc.status_code == 404
        return JSONResponse(status_code=503 if missing else 502, content={'detail':
            'Mô hình chưa sẵn sàng. Hãy tải mô hình đã chọn trong Ollama rồi thử lại.' if missing else
            'Dịch vụ mô hình chưa xử lý được yêu cầu. Hãy kiểm tra cấu hình và tài nguyên máy.'})
    app.add_exception_handler(httpx.TimeoutException, timeout_handler)
    app.add_exception_handler(httpx.ConnectError, connection_handler)
    app.add_exception_handler(ConnectionError, connection_handler)
    app.add_exception_handler(ResponseError, model_handler)
