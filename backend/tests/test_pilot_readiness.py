import io
import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from contextlib import closing, redirect_stdout
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
import httpx
from fastapi.testclient import TestClient
from pydantic import SecretStr
from app.core.config import Settings
from app.main import app
from app.preflight import check_storage, main as preflight_main
from app.rag.index_version import collection_name
from app.services import readiness


class ReadinessTests(unittest.TestCase):
    def setUp(self):
        readiness._inventory = None
        self.addCleanup(setattr, readiness, '_inventory', None)
        self.settings = Settings(_env_file=None)
        self.configured = patch('app.services.readiness.get_settings', return_value=self.settings)
        self.configured.start(); self.addCleanup(self.configured.stop)
        self.client = TestClient(app)

    def test_live_is_independent_of_models_and_ready_returns_503_without_storage_access(self):
        with patch.object(readiness, '_read_inventory', side_effect=RuntimeError('SECRET_PRIVATE_PATH')), \
             patch('app.core.database.SessionLocal', side_effect=AssertionError('Private DB opened')), \
             patch('app.core.database.public_session_factory', side_effect=AssertionError('Public DB opened')):
            self.assertEqual(self.client.get('/health').status_code, 200)
            response = self.client.get('/ready')
            self.assertEqual(response.status_code, 503)
            self.assertFalse(response.json()['data']['ready'])
            self.assertNotIn('SECRET_PRIVATE_PATH', response.text)
            self.assertEqual(response.headers['cache-control'], 'no-store')

    def test_missing_models_report_exact_cause_and_openai_never_claims_connectivity_verified(self):
        self.settings.openai_api_key = SecretStr('NEVER_RETURN_THIS_KEY')
        for names, expected in [(set(), 'embedding_missing'), ({self.settings.embedding_model}, 'model_missing'),
                                ({self.settings.embedding_model, 'qwen2.5:7b'}, 'ready')]:
            with patch.object(readiness, 'model_inventory', return_value=(True, names)):
                models, checks = readiness.model_status()
            self.assertEqual(models[0]['reason'], expected)
            self.assertEqual(models[0]['ready'], expected == 'ready')
            self.assertFalse(models[1]['ready'])
            self.assertEqual(models[2]['reason'], 'embedding_missing' if not names else 'api_configured')
            self.assertNotIn('NEVER_RETURN_THIS_KEY', json.dumps(models))
            self.assertEqual(checks['default_model'], 'qwen2.5:7b' in names)

    def test_ready_when_default_and_embedding_installed_llama_is_optional(self):
        with patch.object(readiness, '_read_inventory', return_value=frozenset({'qwen2.5:7b', self.settings.embedding_model})):
            response = self.client.get('/ready')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()['data']['ready'])
        self.assertTrue(readiness._installed('embedding', {'embedding:latest'}))
        self.assertFalse(readiness._installed('qwen2.5:7b', {'qwen2.5:72b', 'qwen2.5:7b-other'}))

    def test_inventory_cached_across_concurrent_requests_expires_and_changes_url(self):
        now = [0]
        with patch.object(readiness, '_read_inventory', return_value=frozenset()) as probe, \
             patch.object(readiness, 'monotonic', side_effect=lambda: now[0]):
            with ThreadPoolExecutor(max_workers=8) as pool:
                results = list(pool.map(lambda _: readiness.model_inventory(), range(24)))
            self.assertTrue(all(result == (True, frozenset()) for result in results))
            self.assertEqual(probe.call_count, 1)
            now[0] = 16
            readiness.model_inventory()
            self.assertEqual(probe.call_count, 2)
            readiness.model_inventory('http://other-host:11434')
            self.assertEqual(probe.call_count, 3)

    def test_inventory_transport_bounded_validated_and_failure_recovers(self):
        original_client = httpx.Client
        responses = [httpx.Response(200, json={'models': [{'name': 'qwen2.5:7b'}]}),
                     httpx.Response(200, json={'models': 'invalid'}), httpx.Response(200, content=b'x'*(1024*1024+1)),
                     httpx.Response(401, json={'error': 'secret'}), httpx.Response(302, headers={'Location': 'http://other/'})]
        for response in responses:
            with patch.object(readiness.httpx, 'Client', side_effect=lambda **kwargs: original_client(
                    transport=httpx.MockTransport(lambda request: response), **kwargs)):
                if response is responses[0]:
                    self.assertEqual(readiness._read_inventory('http://ollama'), frozenset({'qwen2.5:7b'}))
                else:
                    with self.assertRaises((ValueError, httpx.HTTPError)):
                        readiness._read_inventory('http://ollama')
        now = [0]
        with patch.object(readiness, '_read_inventory', side_effect=[OSError(), frozenset({'ready'})]) as probe, \
             patch.object(readiness, 'monotonic', side_effect=lambda: now[0]):
            self.assertFalse(readiness.model_inventory()[0])
            now[0] = 2
            self.assertFalse(readiness.model_inventory()[0])
            self.assertEqual(probe.call_count, 1)
            now[0] = 4
            self.assertEqual(readiness.model_inventory(), (True, frozenset({'ready'})))

    def test_request_ids_unique_and_server_failures_do_not_leak_exception_or_body(self):
        first = self.client.get('/health')
        second = self.client.get('/missing?token=PRIVATE_SECRET')
        self.assertRegex(first.headers['x-request-id'], r'^[a-f0-9]{32}$')
        self.assertNotEqual(first.headers['x-request-id'], second.headers['x-request-id'])
        with patch('app.api.routes.answer', side_effect=RuntimeError('PRIVATE_SECRET_KEY_AND_SOURCE')):
            response = self.client.post('/chat', json={'question': 'PRIVATE_PROMPT', 'scope': 'public'})
        self.assertEqual(response.status_code, 500)
        self.assertNotIn('PRIVATE_SECRET', response.text)
        self.assertNotIn('PRIVATE_PROMPT', response.text)
        self.assertIn(response.headers['x-request-id'], response.json()['detail'])


class PreflightTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.settings = Settings(_env_file=None, database_url=f'sqlite:///{self.root}/private.db',
            public_database_url=f'sqlite:///{self.root}/public.db', upload_dir=str(self.root/'private'),
            public_upload_dir=str(self.root/'public'), chroma_dir=str(self.root/'index-private'),
            public_chroma_dir=str(self.root/'index-public'))
        self.settings.upload_path.mkdir()
        self.file = self.settings.upload_path/'doc.pdf'; self.file.write_bytes(b'PRIVATE_CANARY')
        self.metadata = self.root/'private.db'
        with closing(sqlite3.connect(self.metadata, isolation_level=None)) as db:
            db.executescript('CREATE TABLE documents (id TEXT PRIMARY KEY, filepath TEXT);')
            db.execute('INSERT INTO documents VALUES (?,?)', ('doc', str(self.file)))
        self.index = Path(self.settings.chroma_dir)
        self.lexical = self.index/'lexical'/(collection_name(self.settings)+'.sqlite3')
        self.lexical.parent.mkdir(parents=True)
        (self.index/'chroma.sqlite3').write_bytes(b'placeholder: contents not checked')
        with closing(sqlite3.connect(self.lexical, isolation_level=None)) as db:
            db.executescript("CREATE TABLE chunks(document_id TEXT); CREATE TABLE state(key TEXT, value INTEGER); INSERT INTO state VALUES ('dirty', 0);")
            db.execute('INSERT INTO chunks VALUES (?)', ('doc',))

    def test_clean_check_is_read_only_and_scope_separate(self):
        paths = [self.file, self.metadata, self.lexical, self.index/'chroma.sqlite3']
        before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in paths}
        self.assertTrue(check_storage(self.settings, 'private')['ready'])
        public = check_storage(self.settings, 'public')
        self.assertFalse(public['ready'])
        self.assertEqual(public['issue'], 'metadata_missing_verify_storage_path')
        self.assertFalse((self.root/'public.db').exists())
        self.assertFalse(Path(self.settings.public_chroma_dir).exists())
        self.assertEqual(before, {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in paths})

    def test_missing_or_outside_files_unindexed_orphan_and_dirty_index_detected(self):
        self.file.unlink()
        with closing(sqlite3.connect(self.metadata, isolation_level=None)) as db:
            db.execute('INSERT INTO documents VALUES (?,?)', ('other', str(self.root/'outside.pdf')))
        with closing(sqlite3.connect(self.lexical, isolation_level=None)) as db:
            db.execute("INSERT INTO chunks VALUES ('orphan')")
            db.execute('UPDATE state SET value=1')
        result = check_storage(self.settings, 'private')
        self.assertFalse(result['ready'])
        self.assertEqual([result[key] for key in ('files_missing','files_outside_root','unindexed_documents','orphan_index_documents')], [1,1,1,1])
        self.assertEqual(result['issue'], 'lexical_rebuild_pending')
        self.assertNotIn(str(self.root), json.dumps(result))
        self.assertNotIn('PRIVATE_CANARY', json.dumps(result))

    def test_changed_embedding_flags_old_index_without_creating_new_collection(self):
        self.settings.embedding_model = 'new-embedding'
        result = check_storage(self.settings, 'private')
        self.assertFalse(result['ready'])
        self.assertEqual(result['unindexed_documents'], 1)
        self.assertEqual(len(list(self.lexical.parent.iterdir())), 1)

    def test_signature_identical_to_existing_v5(self):
        signature = json.dumps({'version': 5, 'embedding': self.settings.embedding_model,
            'instruction': self.settings.embedding_query_instruction, 'chunk_size': self.settings.chunk_size,
            'chunk_overlap': self.settings.chunk_overlap}, sort_keys=True)
        self.assertEqual(collection_name(self.settings), 'documents_v5_'+hashlib.sha256(signature.encode()).hexdigest()[:16])

    def test_corrupt_metadata_safe_error_and_no_auto_repair(self):
        self.metadata.write_bytes(b'broken PRIVATE_SECRET')
        result = check_storage(self.settings, 'private')
        self.assertFalse(result['ready'])
        self.assertEqual(result['issue'], 'storage_check_failed')
        self.assertEqual(self.metadata.read_bytes(), b'broken PRIVATE_SECRET')

    def test_cli_exit_code_and_redacted_json_for_offline_and_online_checks(self):
        self.settings.internal_access_token = SecretStr('test-private-token-never-printed-0123456789')
        output = io.StringIO()
        with patch('app.preflight.get_settings', return_value=self.settings), \
             patch('sys.argv', ['preflight', '--scope', 'private', '--skip-models']), redirect_stdout(output):
            code = preflight_main()
        self.assertEqual(code, 0)
        result = json.loads(output.getvalue())
        self.assertTrue(result['ready'])
        self.assertTrue(result['model_probe_skipped'])
        self.assertNotIn('test-private-token', output.getvalue())
        with patch('app.preflight.get_settings', return_value=self.settings), \
             patch('app.preflight.model_status', return_value=([], {'ollama':False})), \
             patch('sys.argv', ['preflight', '--scope', 'private']), redirect_stdout(io.StringIO()):
            self.assertEqual(preflight_main(), 1)
        self.settings.internal_access_token = SecretStr('')
        with patch('app.preflight.get_settings', return_value=self.settings), \
             patch('sys.argv', ['preflight', '--scope', 'private', '--skip-models']), redirect_stdout(io.StringIO()):
            self.assertEqual(preflight_main(), 1)
