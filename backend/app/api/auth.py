from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, SecretStr
from app.core.access import COOKIE, authenticated, check_origin, issue_session, revoke_session, token_valid
from app.core.config import get_settings
from app.utils.response import ok

router = APIRouter(prefix='/auth', tags=['Access'])


class Login(BaseModel):
    token: SecretStr = SecretStr('')


@router.get('/session')
def access_session(request: Request):
    return ok({'private_access':authenticated(request),
               'private_configured':bool(get_settings().internal_access_token.get_secret_value().strip())})


@router.post('/login')
def login(payload: Login, request: Request, response: Response):
    if request.headers.get('origin'):
        check_origin(request)
    if not token_valid(payload.token.get_secret_value()):
        raise HTTPException(401, 'Khóa truy cập nội bộ không hợp lệ')
    response.set_cookie(COOKIE, issue_session(), max_age=get_settings().session_max_age,
                        httponly=True, secure=get_settings().session_cookie_secure or request.url.scheme=='https',
                        samesite='lax', path='/')
    return ok({'private_access':True})


@router.post('/logout')
def logout(request: Request, response: Response):
    check_origin(request)
    revoke_session(request)
    response.delete_cookie(COOKIE, path='/', httponly=True, samesite='lax',
                           secure=get_settings().session_cookie_secure or request.url.scheme=='https')
    return ok({'private_access':False})
