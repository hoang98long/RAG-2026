import io
import tempfile
import time
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Literal
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from auth_helpers import internal_client
from langchain_core.documents import Document as Chunk
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from app.core.config import Settings
from app.core.database import Base, get_scope_db
from app.main import app
from app.models.models import Document


class UploadRetryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name)
        self.settings=Settings(_env_file=None,database_url=f'sqlite:///{root}/private.db',public_database_url=f'sqlite:///{root}/public.db',
            upload_dir=str(root/'private'),public_upload_dir=str(root/'public'),chroma_dir=str(root/'private_index'),public_chroma_dir=str(root/'public_index'))
        self.factories={}
        for scope in ('private','public'):
            engine=create_engine(getattr(self.settings,'database_url' if scope=='private' else 'public_database_url'))
            self.addCleanup(engine.dispose)
            Base.metadata.create_all(engine)
            self.factories[scope]=sessionmaker(bind=engine)
        def scoped(scope:Literal['private','public']='private'):
            with self.factories[scope]() as db:yield db
        app.dependency_overrides[get_scope_db]=scoped
        self.addCleanup(app.dependency_overrides.clear)
        self.client=internal_client(self, app)
        self.stores={'private':MagicMock(),'public':MagicMock()}
        for store in self.stores.values():
            store.add.side_effect=lambda identifier,filename,chunks:len(list(chunks))
        for target,values in [('app.services.document_service.get_settings',{'return_value':self.settings}),
                              ('app.services.document_service.get_vector_store',{'side_effect':lambda scope='private':self.stores[scope]}),
                              ('app.services.document_service.iter_chunks',{'side_effect':lambda path:iter([Chunk(page_content='Text')])})]:
            patcher=patch(target,**values);patcher.start();self.addCleanup(patcher.stop)
        self.key=str(uuid.uuid4())

    def upload(self,content=b'original',scope='private',filename='source.pdf',key=None):
        return self.client.post('/documents/upload',params={'scope':scope},headers={'Idempotency-Key':key or self.key},
            files={'files':(filename,content,'application/pdf')})

    def test_same_request_returns_original_record_without_embedding_again(self):
        first,second=self.upload(),self.upload()
        self.assertEqual(first.status_code,200,first.text)
        self.assertEqual(second.json()['data'][0]['id'],first.json()['data'][0]['id'])
        self.assertEqual(self.stores['private'].add.call_count,1)
        with self.factories['private']() as db:
            records=db.scalars(select(Document)).all()
            self.assertEqual(len(records),1)
            self.assertEqual(Path(records[0].filepath).read_bytes(),b'original')

    def test_key_cannot_replace_original_contents_or_filename(self):
        self.assertEqual(self.upload().status_code,200)
        self.assertEqual(self.upload(b'changed').status_code,409)
        self.assertEqual(self.upload(filename='other.pdf').status_code,409)
        self.assertEqual(self.stores['private'].add.call_count,1)
        self.assertEqual(self.upload().status_code,200)

    def test_retry_identifier_has_independent_namespace_per_scope(self):
        private=self.upload(b'private')
        public=self.upload(b'public',scope='public')
        self.assertEqual(private.status_code,200)
        self.assertEqual(public.status_code,200,public.text)
        self.assertEqual(private.json()['data'][0]['id'],public.json()['data'][0]['id'])
        self.assertEqual(self.stores['private'].add.call_count,1)
        self.assertEqual(self.stores['public'].add.call_count,1)

    def test_concurrent_retry_ingests_only_once(self):
        def add(identifier,filename,chunks):
            time.sleep(.05)
            return len(list(chunks))
        self.stores['private'].add.side_effect=add
        with ThreadPoolExecutor(max_workers=2) as executor:
            results=list(executor.map(lambda index:self.upload(),range(2)))
        self.assertEqual([result.status_code for result in results],[200,200])
        self.assertEqual(self.stores['private'].add.call_count,1)

    def test_invalid_identifiers_and_multifile_retries_are_rejected(self):
        self.assertEqual(self.upload(key='invalid').status_code,400)
        response=self.client.post('/documents/upload',headers={'Idempotency-Key':self.key},files=[('files',('a.pdf',b'a')),('files',('b.pdf',b'b'))])
        self.assertEqual(response.status_code,400)
        self.stores['private'].add.assert_not_called()


if __name__=='__main__':unittest.main()
