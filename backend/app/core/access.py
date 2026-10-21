"""Private access, short-lived opaque browser sessions and origin checks."""
import hashlib
import hmac
import secrets
import time
from threading import Lock
from fastapi import HTTPException, Request
from app.core.config import get_settings

COOKIE = 'documind_session'
_sessions = {}
_lock = Lock()


def _key():
    return get_settings().internal_access_token.get_secret_value().strip()


def token_valid(value: str) -> bool:
    expected = _key()
    return bool(expected and len(value) <= 512 and hmac.compare_digest(value.encode(), expected.encode()))


def check_origin(request: Request):
    origin = request.headers.get('origin')
    allowed = {item.strip().rstrip('/') for item in get_settings().cors_origins.split(',') if item.strip()}
    allowed.add(f'{request.url.scheme}://{request.url.netloc}')
    if not origin or origin.rstrip('/') not in allowed:
        raise HTTPException(403, 'Nguồn yêu cầu không được phép thực hiện thao tác này')


def authenticated(request: Request) -> bool:
    authorization = request.headers.get('authorization')
    if authorization is not None:
        scheme, _, value = authorization.partition(' ')
        return scheme.lower() == 'bearer' and token_valid(value)
    cookie = request.cookies.get(COOKIE, '')
    if not cookie or len(cookie) > 128 or not _key():
        return False
    digest = hashlib.sha256(cookie.encode()).hexdigest()
    with _lock:
        entry = _sessions.get(digest)
        if entry is None:
            return False
        expires, fingerprint = entry
        if expires <= time.monotonic() or fingerprint != hashlib.sha256(_key().encode()).digest():
            _sessions.pop(digest, None)
            return False
    return True


def require_private_access(request: Request):
    if not authenticated(request):
        raise HTTPException(401, 'Cần đăng nhập quyền nội bộ để sử dụng chức năng này', headers={'WWW-Authenticate':'Bearer'})
    if request.method not in {'GET', 'HEAD', 'OPTIONS'} and not request.headers.get('authorization'):
        check_origin(request)


def issue_session() -> str:
    value = secrets.token_urlsafe(32)
    now = time.monotonic()
    with _lock:
        for digest in list(_sessions):
            if _sessions[digest][0] <= now:
                _sessions.pop(digest, None)
        while len(_sessions) >= 256:
            _sessions.pop(next(iter(_sessions)))
        _sessions[hashlib.sha256(value.encode()).hexdigest()] = (
            now + get_settings().session_max_age, hashlib.sha256(_key().encode()).digest())
    return value


def revoke_session(request: Request):
    value = request.cookies.get(COOKIE, '')
    with _lock:
        _sessions.pop(hashlib.sha256(value.encode()).hexdigest(), None)

class ProtectedWriteMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'http':
            path = scope['path'].rstrip('/')
            protected = ((scope['method'] == 'POST' and path in {'/documents/upload','/report'})
                         or (scope['method'] == 'DELETE' and path.startswith('/documents/')))
            if protected:
                try:
                    require_private_access(Request(scope))
                except HTTPException as exc:
                    from fastapi.responses import JSONResponse
                    return await JSONResponse({'detail':exc.detail},status_code=exc.status_code,headers=exc.headers)(scope,receive,send)
        return await self.app(scope,receive,send)
