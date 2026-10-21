"""Run backend tests in a child process with disposable default storage and no real .env."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

CHILD = '''
import os
import sys
import unittest
from pathlib import Path
backend = Path(sys.argv[1])
sys.path[:0] = [str(backend), str(backend/'tests')]
from app.core.config import Settings
# CWD is a new temporary directory. Clear inherited application settings too.
for field in Settings.model_fields:
    os.environ.pop(field.upper(), None)
root = Path.cwd()
os.environ.update(DATABASE_URL='sqlite:///'+str(root/'private.db'),
    PUBLIC_DATABASE_URL='sqlite:///'+str(root/'public.db'),
    CHROMA_DIR=str(root/'private-index'), PUBLIC_CHROMA_DIR=str(root/'public-index'),
    UPLOAD_DIR=str(root/'private-files'), PUBLIC_UPLOAD_DIR=str(root/'public-files'),
    OPENAI_API_KEY='', INTERNAL_ACCESS_TOKEN='', OLLAMA_BASE_URL='http://127.0.0.1:9')
from loguru import logger
logger.remove()
suite = unittest.defaultTestLoader.discover(str(backend/'tests'))
assert suite.countTestCases() > 0, 'No tests discovered'
print('Running isolated backend suite:', suite.countTestCases(), 'tests', flush=True)
result = unittest.TextTestRunner(verbosity=1).run(suite)
raise SystemExit(not result.wasSuccessful())
'''


def main():
    backend = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix='documind-tests-') as temporary:
        result = subprocess.run([sys.executable, '-c', CHILD, str(backend)], cwd=temporary,
            env={**os.environ, 'PYTHONIOENCODING':'utf-8'}, capture_output=True, text=True, encoding='utf-8', errors='replace',
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        sys.stdout.write(result.stdout)
        sys.stderr.write(result.stderr)
        return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
