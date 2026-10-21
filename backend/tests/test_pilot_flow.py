"""Real DOCX -> SQLite/Chroma/FTS -> scoped RAG -> verified source -> deletion.
Only model responses/embeddings are simulated; no existing user storage is opened.
"""
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from zipfile import ZipFile
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import Settings
from app.core.database import Base
from app.main import app
from app.preflight import check_storage
from app.rag.vector_store import VectorStore
from app.services.rag_service import CitationQuote, GroundingReview
from auth_helpers import TOKEN


class OfflineEmbedding:
    def __init__(self, **kwargs): pass
    def embed_documents(self, texts): return [[1.0, 0.0] for _ in texts]
    def embed_query(self, text): return [1.0, 0.0]


def docx(text):
    buffer = io.BytesIO()
    with ZipFile(buffer, 'w') as archive:
        archive.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>'+text+'</w:t></w:r></w:p></w:body></w:document>')
    return buffer.getvalue()


class PilotFlowTests(unittest.TestCase):
    def test_ingest_retry_public_answer_exact_source_and_scoped_delete(self):
        temporary = tempfile.TemporaryDirectory(prefix='documind-flow-'); self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        settings = Settings(_env_file=None, internal_access_token=TOKEN, openai_api_key='test-not-a-real-key',
            database_url=f'sqlite:///{root}/private.db', public_database_url=f'sqlite:///{root}/public.db',
            upload_dir=str(root/'private'), public_upload_dir=str(root/'public'),
            chroma_dir=str(root/'index-private'), public_chroma_dir=str(root/'index-public'),
            rerank_backend='off', query_expansion=False, grounding_verification=True)
        for module in ['app.core.access','app.api.auth','app.api.routes','app.core.public_limits',
                       'app.services.document_service','app.services.rag_service','app.services.model_provider','app.services.report_service',
                       'app.services.source_catalogue','app.rag.vector_store','app.rag.evidence','app.rag.reranking','app.rag.chunking']:
            current = patch(module+'.get_settings', return_value=settings); current.start(); self.addCleanup(current.stop)
        factories = {}
        for scope in ('private','public'):
            engine = create_engine(f'sqlite:///{root}/{scope}.db'); self.addCleanup(engine.dispose)
            Base.metadata.create_all(engine); factories[scope] = sessionmaker(bind=engine)
        targets = [('app.core.database.SessionLocal', {'wraps':factories['private']}),
                   ('app.core.database.public_session_factory', {'return_value':factories['public']}),
                   ('app.services.rag_service.public_session_factory', {'return_value':factories['public']}),
                   ('app.rag.vector_store.OllamaEmbeddings', {'new':OfflineEmbedding})]
        private_factory = None
        for target, kwargs in targets:
            current = patch(target, **kwargs); mocked = current.start(); self.addCleanup(current.stop)
            if target.endswith('SessionLocal'): private_factory = mocked
        stores = {scope:VectorStore(scope) for scope in ('private','public')}
        for store in stores.values(): self.addCleanup(store.client._system.stop)
        for target in ['app.api.routes.get_vector_store','app.services.document_service.get_vector_store','app.services.rag_service.get_vector_store','app.services.report_service.get_vector_store']:
            current = patch(target, side_effect=lambda scope='private': stores[scope]); current.start(); self.addCleanup(current.stop)
        llm = MagicMock()
        llm.invoke.return_value = AIMessage(content='Public warranty 24 months [S1]')
        llm.with_structured_output.return_value.invoke.return_value = GroundingReview(supported=True, issues=[],
            citations=[CitationQuote(source_id='S1', claim='24 months', quote='Public warranty 24 months.')])
        current = patch('app.services.rag_service._llm', return_value=llm); current.start(); self.addCleanup(current.stop)
        client = TestClient(app, headers={'Authorization':f'Bearer {TOKEN}'})
        ids = {'private':'11111111-1111-4111-8111-111111111111','public':'22222222-2222-4222-8222-222222222222'}
        bodies = {'private':docx('PRIVATE_CANARY_ONLY 99 months.'), 'public':docx('Public warranty 24 months.')}
        for scope in ('private','public'):
            for _ in range(2):
                response = client.post('/documents/upload?scope='+scope, headers={'Idempotency-Key':ids[scope]},
                    files={'files':(scope+'.docx', bodies[scope], 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')})
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()['data'][0]['id'], ids[scope])
            self.assertEqual(stores[scope].collection.count(), 1)
            self.assertTrue(check_storage(settings, scope)['ready'])
        for model in ('qwen2.5:7b','openai'):
            private_factory.reset_mock(); llm.reset_mock()
            response = client.post('/chat', json={'question':'Warranty duration?', 'scope':'public', 'model':model})
            self.assertEqual(response.status_code, 200, response.text)
            data = response.json()['data']
            self.assertIn('24 months', data['answer'])
            self.assertNotIn('PRIVATE_CANARY', response.text)
            self.assertEqual([source['scope'] for source in data['sources']], ['public'])
            source = data['sources'][0]
            self.assertEqual(source['document_id'], ids['public'])
            params = dict(scope='public', chunk=source['chunk_index'], version=source['index_version'], digest=source['digest'])
            reader = client.get('/documents/'+ids['public']+'/content', params=params)
            self.assertEqual(reader.status_code, 200, reader.text)
            self.assertIn('24 months', reader.text)
            params['digest'] = '0000000000000000'
            self.assertEqual(client.get('/documents/'+ids['public']+'/content', params=params).status_code, 409)
            private_factory.assert_not_called()
            self.assertTrue(llm.with_structured_output.called, 'Grounding reviewer must run')
            self.assertNotIn('PRIVATE_CANARY', repr(llm.mock_calls))
        self.assertEqual(client.post('/chat', json={'question':'Read secrets', 'scope':'private', 'model':'openai'}).status_code, 403)
        llm.invoke.return_value = AIMessage(content='PRIVATE_CANARY_ONLY 99 months [S1]')
        llm.with_structured_output.return_value.invoke.return_value = GroundingReview(supported=True, issues=[],
            citations=[CitationQuote(source_id='S1', claim='99 months', quote='PRIVATE_CANARY_ONLY 99 months.')])
        response = client.post('/report', json={'template':'technical','title':'Private warranty','document_ids':[ids['private']],
                                               'sections':['Facts','Conditions']})
        self.assertEqual(response.status_code, 200, response.text)
        report = response.json()['data']
        self.assertEqual(report['coverage']['verified_sections'], 2)
        self.assertEqual({item['document_id'] for item in report['sources']}, {ids['private']})
        self.assertNotIn('Public warranty', report['content'])
        self.assertEqual(client.post('/report', json={'template':'technical','title':'T','document_ids':[ids['public']]}).status_code, 404)
        self.assertEqual(client.post('/report', json={'template':'technical','title':'T','model':'openai'}).status_code, 422)
        self.assertEqual(client.delete('/documents/'+ids['public']+'?scope=public').status_code, 200)
        self.assertEqual(stores['public'].collection.count(), 0)
        self.assertEqual(stores['private'].collection.count(), 1)
        self.assertTrue((settings.upload_path/(ids['private']+'.docx')).is_file())
        self.assertEqual(client.get('/documents/'+ids['public']+'/file?scope=public').status_code, 404)
        self.assertEqual(client.get('/documents/paged?scope=public').json()['data']['total'], 0)
