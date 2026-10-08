"""Limit raw multipart bodies before FastAPI finishes parsing/spooling them."""
from fastapi import HTTPException
from fastapi.responses import JSONResponse


class UploadBodyLimitMiddleware:
    def __init__(self, app, max_bytes: int):
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['method'] != 'POST' or scope['path'].rstrip('/') != '/documents/upload':
            return await self.app(scope, receive, send)
        detail = f'Yêu cầu upload vượt giới hạn {self.max_bytes // (1024 * 1024)} MiB'
        headers = dict(scope.get('headers', []))
        length = headers.get(b'content-length')
        if length and length.isdigit() and int(length) > self.max_bytes:
            return await JSONResponse({'detail': detail}, status_code=413)(scope, receive, send)
        used = 0

        async def limited_receive():
            nonlocal used
            message = await receive()
            if message['type'] == 'http.request':
                used += len(message.get('body', b''))
                if used > self.max_bytes:
                    raise HTTPException(413, detail)
            return message

        return await self.app(scope, limited_receive, send)
