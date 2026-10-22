"""Limit raw multipart bodies before FastAPI finishes parsing/spooling them."""
from fastapi import HTTPException
from fastapi.responses import JSONResponse


class UploadBodyLimitMiddleware:
    def __init__(self, app, max_bytes: int):
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['method'] != 'POST':
            return await self.app(scope, receive, send)
        path = scope['path'].rstrip('/')
        if path == '/documents/upload':
            max_bytes = self.max_bytes
        elif path in {'/chat','/chat/direct','/report'}:
            max_bytes = 64 * 1024
        elif path in {'/auth/login','/auth/logout'}:
            max_bytes = 16 * 1024
        else:
            return await self.app(scope, receive, send)
        detail = f'Yêu cầu upload vượt giới hạn {self.max_bytes // (1024 * 1024)} MiB'
        if path != '/documents/upload':
            detail = 'Nội dung yêu cầu vượt giới hạn kích thước cho phép'
        headers = dict(scope.get('headers', []))
        length = headers.get(b'content-length')
        if length and length.isdigit() and int(length) > max_bytes:
            return await JSONResponse({'detail': detail}, status_code=413)(scope, receive, send)
        used = 0

        async def limited_receive():
            nonlocal used
            message = await receive()
            if message['type'] == 'http.request':
                used += len(message.get('body', b''))
                if used > max_bytes:
                    raise HTTPException(413, detail)
            return message

        return await self.app(scope, limited_receive, send)
