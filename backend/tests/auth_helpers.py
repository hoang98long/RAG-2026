"""Authenticated clients for existing route tests; auth itself is tested separately."""
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.core.config import Settings

TOKEN = 'test-internal-access-token-0123456789abcdef'


def internal_client(case, app):
    settings = Settings(_env_file=None, internal_access_token=TOKEN)
    configured = patch('app.core.access.get_settings', return_value=settings)
    configured.start()
    case.addCleanup(configured.stop)
    return TestClient(app, headers={'Authorization':f'Bearer {TOKEN}'})
