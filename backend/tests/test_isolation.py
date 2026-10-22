import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import httpx
from fastapi import HTTPException
from fastapi.testclient import TestClient
from auth_helpers import internal_client
from langchain_core.documents import Document as Chunk
from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from pydantic import ValidationError
from app.core.config import Settings
from app.core.database import Base, get_db, get_scope_db, public_session_factory
from app.main import app
from app.models.models import Document, ChatHistory
from app.rag.evidence import EvidenceResult, QueryPlan, retrieve_evidence
from app.rag.vector_store import VectorStore
from app.services.model_provider import OpenAIChat, assert_public_sources, validate_selection
from app.services.rag_service import answer


class FakeEmbedding:
    def __init__(self, **kwargs): pass
    def embed_documents(self, texts): return [[1.0, 0.0] for text in texts]
    def embed_query(self, text): return [1.0, 0.0]


class IsolationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.settings = Settings(_env_file=None, database_url=f'sqlite:///{self.root}/private.db',
            public_database_url=f'sqlite:///{self.root}/public.db', chroma_dir=str(self.root/'private_index'),
            public_chroma_dir=str(self.root/'public_index'), upload_dir=str(self.root/'private_upload'),
            public_upload_dir=str(self.root/'public_upload'), openai_api_key='test-key-not-a-secret',
            query_expansion=False, rerank_backend='off', grounding_verification=False)
        self.factories = {}
        for scope in ('private','public'):
            url = self.settings.database_url if scope == 'private' else self.settings.public_database_url
            engine = create_engine(url)
            self.addCleanup(engine.dispose)
            Base.metadata.create_all(engine)
            self.factories[scope] = sessionmaker(bind=engine)
        def private_db():
            with self.factories['private']() as db: yield db
        def scoped_db(scope: str = 'private'):
            with self.factories[scope]() as db: yield db
        app.dependency_overrides[get_db] = private_db
        app.dependency_overrides[get_scope_db] = scoped_db
        self.addCleanup(app.dependency_overrides.clear)
        self.client = internal_client(self, app)

    def test_storage_configuration_rejects_shared_db_or_directories(self):
        for values in [{'public_database_url': self.settings.database_url},
                       {'public_chroma_dir': self.settings.chroma_dir},
                       {'public_upload_dir': str(Path(self.settings.upload_dir)/'public')}]:
            with self.assertRaises(ValidationError):
                Settings(_env_file=None, **{**self.settings.model_dump(), **values})

    def test_real_chroma_same_document_id_is_isolated_and_delete_is_scoped(self):
        with patch('app.rag.vector_store.get_settings', return_value=self.settings), \
             patch('app.rag.vector_store.OllamaEmbeddings', FakeEmbedding):
            private, public = VectorStore('private'), VectorStore('public')
            try:
                private.add('same-id','confidential.pdf',[Chunk(page_content='PRIVATE_CANARY',metadata={'page':1})])
                public.add('same-id','public.pdf',[Chunk(page_content='PUBLIC_FACT',metadata={'page':2})])
                self.assertNotEqual(private.chroma_dir, public.chroma_dir)
                self.assertEqual([item['content'] for item in public.candidates('PRIVATE_CANARY')], ['PUBLIC_FACT'])
                self.assertEqual([item['scope'] for item in public.candidates('fact')], ['public'])
                public.delete_document('same-id')
                self.assertEqual(public.collection.count(),0)
                self.assertEqual(private.collection.count(),1)
                self.assertEqual(private.document_page('same-id')['chunks'][0]['content'],'PRIVATE_CANARY')
            finally:
                private.client._system.stop()
                public.client._system.stop()

    def test_upload_catalogue_file_delete_use_only_selected_corpus(self):
        stores = {'private':MagicMock(),'public':MagicMock()}
        stores['private'].add.side_effect=lambda identifier,filename,chunks:len(list(chunks))
        stores['public'].add.side_effect=lambda identifier,filename,chunks:len(list(chunks))
        def store(scope='private'): return stores[scope]
        with patch('app.services.document_service.get_settings',return_value=self.settings), \
             patch('app.api.routes.get_settings',return_value=self.settings), \
             patch('app.services.document_service.get_vector_store',side_effect=store), \
             patch('app.services.document_service.iter_chunks',side_effect=lambda path: iter([Chunk(page_content='Text')])):
            ids={}
            for scope in ('private','public'):
                response=self.client.post('/documents/upload',params={'scope':scope},files={'files':(f'{scope}.pdf',b'pdf','application/pdf')})
                self.assertEqual(response.status_code,200,response.text)
                ids[scope]=response.json()['data'][0]['id']
                with self.factories[scope]() as db:
                    record=db.get(Document,ids[scope])
                    self.assertTrue(Path(record.filepath).is_relative_to(self.settings.scope_upload_path(scope)))
            public=self.client.get('/documents/paged?scope=public').json()['data']['items']
            self.assertEqual([record['filename'] for record in public],['public.pdf'])
            self.assertEqual(self.client.get(f"/documents/{ids['private']}/file?scope=public").status_code,404)
            self.assertEqual(self.client.delete(f"/documents/{ids['private']}?scope=public").status_code,404)
            self.assertEqual(self.client.get(f"/documents/{ids['public']}/file?scope=public").content,b'pdf')
            self.assertEqual(self.client.delete(f"/documents/{ids['public']}?scope=public").status_code,200)
            with self.factories['private']() as db:
                self.assertIsNotNone(db.get(Document,ids['private']))
            stores['private'].delete_document.assert_not_called()
            stores['public'].delete_document.assert_called_once_with(ids['public'])

    def test_openai_private_and_all_blocked_before_any_retrieval(self):
        with patch('app.services.model_provider.get_settings',return_value=self.settings), \
             patch('app.services.rag_service.get_vector_store') as store, \
             patch('app.services.rag_service._llm') as llm:
            for scope in ('private','all'):
                response=self.client.post('/chat',json={'question':'Q','model':'openai','scope':scope})
                self.assertEqual(response.status_code,403,response.text)
            store.assert_not_called()
            llm.assert_not_called()
            response=self.client.post('/chat',json={'question':'Q','model':'unexpected','scope':'public'})
            self.assertEqual(response.status_code,422)

    def test_missing_key_does_not_fall_back_to_private_or_local(self):
        settings=self.settings.model_copy(update={'openai_api_key':Settings(_env_file=None).openai_api_key})
        with patch('app.services.model_provider.get_settings',return_value=settings), \
             patch('app.services.rag_service.get_vector_store') as store:
            response=self.client.post('/chat',json={'question':'Q','model':'openai','scope':'public'})
        self.assertEqual(response.status_code,503)
        store.assert_not_called()

    def test_public_only_answer_does_not_read_private_history_or_passages(self):
        public_source={'scope':'public','document':'public.pdf','document_id':'pub','chunk_index':0,'content':'PUBLIC_FACT','source_id':'S1'}
        result=EvidenceResult([public_source],[public_source],{'completeness_unverified':False})
        llm=MagicMock()
        llm.invoke.return_value=AIMessage(content='PUBLIC_FACT [S1]')
        private_db=MagicMock()
        with patch('app.services.model_provider.get_settings',return_value=self.settings), \
             patch('app.services.rag_service.get_settings',return_value=self.settings), \
             patch('app.services.rag_service._llm',return_value=llm), \
             patch('app.services.rag_service.get_vector_store') as store, \
             patch('app.services.rag_service.retrieve_evidence',return_value=result), \
             patch('app.services.rag_service.public_session_factory',return_value=self.factories['public']):
            answer('Public question',private_db,model='openai',scope='public')
        store.assert_called_once_with('public')
        private_db.assert_not_called()
        private_db.add.assert_not_called()
        private_db.scalars.assert_not_called()
        prompt=llm.invoke.call_args.args[0][-1].content
        self.assertIn('PUBLIC_FACT',prompt)
        self.assertNotIn('PRIVATE_CANARY',prompt)
        with self.factories['public']() as db:
            self.assertEqual(len(db.scalars(select(ChatHistory)).all()),1)
        with self.factories['private']() as db:
            self.assertEqual(len(db.scalars(select(ChatHistory)).all()),0)

    def test_openai_refuses_unscoped_or_private_candidates_and_private_store(self):
        for scope in ('private',None):
            with self.assertRaises(HTTPException): assert_public_sources([{'scope':scope}])
        with self.assertRaises(ValueError):
            retrieve_evidence('Q',[SimpleNamespace(scope='private')],MagicMock(),'openai')
        bad_store=MagicMock(scope='public')
        bad_store.candidates.return_value=[{'scope':'private','content':'PRIVATE_CANARY'}]
        with patch('app.rag.evidence.get_settings',return_value=self.settings):
            with self.assertRaises(HTTPException): retrieve_evidence('Q',[bad_store],MagicMock(),'openai')

    def test_local_models_can_use_public_and_all_without_openai_client(self):
        for scope in ('public','all'):
            result=EvidenceResult([],[],{'completeness_unverified':False})
            with patch('app.services.rag_service.get_settings',return_value=self.settings), \
                 patch('app.services.rag_service._llm',return_value=MagicMock()) as llm, \
                 patch('app.services.rag_service.OpenAIChat') as openai, \
                 patch('app.services.rag_service.get_vector_store') as store, \
                 patch('app.services.rag_service.retrieve_evidence',return_value=result), \
                 patch('app.services.rag_service.public_session_factory',return_value=self.factories['public']):
                answer('Q',MagicMock(),model='llama3.1:70b',scope=scope)
            llm.assert_called_once_with('llama3.1:70b',scope)
            openai.assert_not_called()
            self.assertIn(unittest.mock.call('public'),store.call_args_list)
            self.assertEqual(store.call_count,1 if scope=='public' else 2)

    def test_display_sources_prioritize_the_exact_chunk_cited_in_answer(self):
        evidence=[{'scope':'private','document':'A.pdf','document_id':'a','chunk_index':i,
                   'content':f'Fact {i}','source_id':f'S{i+1}'} for i in range(3)]
        result=EvidenceResult(evidence,evidence[:2],{'completeness_unverified':False})
        llm=MagicMock()
        llm.invoke.return_value=AIMessage(content='Fact 2 [S3]')
        with patch('app.services.rag_service.get_settings',return_value=self.settings), \
             patch('app.services.rag_service._llm',return_value=llm), \
             patch('app.services.rag_service.get_vector_store'), \
             patch('app.services.rag_service.retrieve_evidence',return_value=result):
            text,sources,cached,coverage=answer('Q',MagicMock())
        self.assertEqual([item['chunk_index'] for item in sources],[2])
        self.assertEqual(sources[0]['source_id'],'S3')

    def test_model_list_reveals_readiness_without_key(self):
        with patch('app.api.routes.get_settings',return_value=self.settings), \
             patch('app.services.readiness._read_inventory',return_value=frozenset()):
            response=self.client.get('/chat/models')
        self.assertEqual(response.status_code,200)
        self.assertNotIn('test-key-not-a-secret',response.text)
        self.assertEqual(response.json()['data'][0]['id'],'qwen2.5:7b')
        self.assertTrue(response.json()['data'][2]['configured'])

    def test_real_openai_sdk_stateless_response_and_structured_plan_using_mock_transport(self):
        from openai import OpenAI
        requests=[]
        def handle(request):
            payload=json.loads(request.content)
            requests.append(payload)
            structured='format' in payload.get('text',{})
            content=json.dumps({'queries':['public query'],'exhaustive':False}) if structured else 'PUBLIC_FACT [S1]'
            return httpx.Response(200,json={'id':'resp_test','object':'response','created_at':1,'status':'completed',
                'model':'gpt-4.1-mini','output':[{'id':'msg_test','type':'message','role':'assistant','status':'completed',
                  'content':[{'type':'output_text','text':content,'annotations':[]}]}]})
        with httpx.Client(transport=httpx.MockTransport(handle)) as http_client:
            client=OpenAI(api_key='test-key',http_client=http_client)
            with patch('app.services.model_provider.get_settings',return_value=self.settings), patch('openai.OpenAI',return_value=client):
                adapter=OpenAIChat()
                self.assertEqual(adapter.invoke([HumanMessage(content='PUBLIC_FACT')]).content,'PUBLIC_FACT [S1]')
                plan=adapter.with_structured_output(QueryPlan).invoke([HumanMessage(content='Public question')])
                self.assertEqual(plan.queries,['public query'])
        self.assertEqual(len(requests),2)
        self.assertTrue(all(request['store'] is False for request in requests))
        self.assertTrue(all(request['model'] == self.settings.openai_model for request in requests))
        self.assertTrue(all('reasoning' not in request for request in requests))
        self.assertTrue(all(not request.get('tools') and not request.get('previous_response_id') for request in requests))


if __name__=='__main__': unittest.main()
