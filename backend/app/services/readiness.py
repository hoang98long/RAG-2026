"""Bounded, cached dependency checks; never open a document database or call inference."""
from threading import Lock
from time import monotonic
import json
import httpx
from app.core.config import get_settings

_lock = Lock()
_inventory = None
_MAX_BYTES = 1024 * 1024


def _read_inventory(base_url):
    with httpx.Client(timeout=httpx.Timeout(2.0), trust_env=False, follow_redirects=False) as client:
        with client.stream('GET', base_url.rstrip('/') + '/api/tags') as response:
            response.raise_for_status()
            content = bytearray()
            deadline = monotonic() + 3
            for part in response.iter_bytes():
                content.extend(part)
                if len(content) > _MAX_BYTES or monotonic() > deadline:
                    raise ValueError('Inventory limit exceeded')
    data = json.loads(content)
    if not isinstance(data, dict) or not isinstance(data.get('models'), list):
        raise ValueError('Invalid inventory')
    names = set()
    for item in data['models']:
        if not isinstance(item, dict) or not isinstance(item.get('name'), str):
            raise ValueError('Invalid model')
        names.add(item['name'])
    return frozenset(names)


def model_inventory(base_url=None):
    global _inventory
    base_url = base_url or get_settings().ollama_base_url
    # One probe at a time, cached across health checks, tabs and chat requests.
    with _lock:
        if _inventory and _inventory[0] == base_url and monotonic() < _inventory[1]:
            return _inventory[2:]
        try:
            names, available = _read_inventory(base_url), True
        except Exception:
            names, available = frozenset(), False
        _inventory = (base_url, monotonic() + (15 if available else 3), available, names)
        return available, names


def _installed(model, names):
    return model in names or (':' not in model.rsplit('/', 1)[-1] and model + ':latest' in names)



def direct_model_status(settings=None):
    """Direct chat needs an API key only; never probe Ollama or storage."""
    settings = settings or get_settings()
    configured = bool(settings.openai_api_key.get_secret_value().strip())
    return [dict(id='openai', label=f'OpenAI · {settings.openai_model}', configured=configured, ready=configured,
                 reason='api_configured' if configured else 'api_key_missing',
                 message='Đã cấu hình OpenAI. Quyền mô hình và hạn mức được kiểm tra khi gửi tin nhắn.' if configured else
                         'Máy chủ chưa cấu hình OpenAI API key.')]


def model_status(settings=None):
    settings = settings or get_settings()
    available, names = model_inventory(settings.ollama_base_url)
    embedding = available and _installed(settings.embedding_model, names)
    messages = {
        'ready': 'Đã tìm thấy mô hình và embedding. Lần trả lời đầu có thể cần thời gian nạp mô hình.',
        'ollama_unavailable': 'Chưa kết nối được Ollama. Vui lòng liên hệ quản trị viên hoặc thử lại sau.',
        'embedding_missing': 'Máy chủ chưa có mô hình embedding để tìm kiếm tài liệu.',
        'model_missing': 'Máy chủ chưa tải mô hình trả lời này.',
        'api_key_missing': 'Máy chủ chưa cấu hình OpenAI API key.',
        'api_configured': 'Đã cấu hình OpenAI và embedding. Kết nối API, quyền mô hình và hạn mức sẽ được kiểm tra khi gửi câu hỏi.',
    }
    models = []
    for model, label in [('qwen2.5:7b', 'Qwen 2.5 · 7B (local)'), ('llama3.1:70b', 'Llama 3.1 · 70B (local)'), ('openai', f'OpenAI · {settings.openai_model}')]:
        configured = model != 'openai' or bool(settings.openai_api_key.get_secret_value().strip())
        if not configured:
            reason = 'api_key_missing'
        elif not available:
            reason = 'ollama_unavailable'
        elif not embedding:
            reason = 'embedding_missing'
        elif model == 'openai':
            reason = 'api_configured'
        elif not _installed(model, names):
            reason = 'model_missing'
        else:
            reason = 'ready'
        models.append(dict(id=model, label=label, configured=configured, ready=reason in {'ready', 'api_configured'},
                           reason=reason, message=messages[reason]))
    checks = dict(ollama=available, embedding=embedding, default_model=available and _installed(settings.llm_model, names))
    return models, checks
