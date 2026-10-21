from fastapi import APIRouter
from fastapi.responses import JSONResponse
from app.services.readiness import model_status
from app.utils.response import ok

router = APIRouter(tags=['Health'])


@router.get('/ready')
def readiness():
    _, checks = model_status()
    ready = all(checks.values())
    return JSONResponse(status_code=200 if ready else 503,
                        content=ok({'ready': ready, 'checks': checks}, 'ready' if ready else 'dependencies_unavailable'))
