import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.testclient import TestClient
from langchain_core.documents import Document
from app.core.config import Settings
from app.core.upload_limits import UploadBodyLimitMiddleware
from app.rag.lexical_store import LexicalStore
from app.rag.vector_store import VectorStore
from app.services.document_service import upload_files


class ScaleEmbeddings:
    batches = []

    def __init__(self, **kwargs):
        pass

    def embed_documents(self, texts):
        self.batches.append(len(texts))
        return [[0.0, 1.0] for text in texts]

    def embed_query(self, query):
        return [1.0, 0.0]


class ScaleTests(unittest.TestCase):
    def test_fts_persists_updates_and_deletes_without_query_syntax_injection(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'lexical.sqlite3'
            index = LexicalStore(path)
            index.upsert(['a'], ['bảo hành AB987'], [{'document_id': 'doc', 'filename': 'A.pdf', 'chunk_index': 0}])
            self.assertEqual(LexicalStore(path).search('AB987', 5), ['a'])
            self.assertEqual(index.search('" OR AB987 -*', 5), ['a'])
            index.upsert(['a'], ['bảo hành XY123'], [{'document_id': 'doc', 'filename': 'A.pdf', 'chunk_index': 0}])
            self.assertEqual(index.search('AB987', 5), [])
            self.assertEqual(index.search('XY123', 5), ['a'])
            index.delete_document('doc')
            self.assertEqual(index.search('XY123', 5), [])

    def test_large_catalogue_retrieves_exact_codes_and_only_requested_document(self):
        with tempfile.TemporaryDirectory() as directory:
            index = LexicalStore(Path(directory) / 'lexical.sqlite3')
            for batch in range(20):
                ids, contents, metadata = [], [], []
                for doc in range(batch * 50, (batch + 1) * 50):
                    for chunk in range(4):
                        ids.append(f'{doc}:{chunk}')
                        contents.append(f'Regulation CODE{doc:06d} clause {chunk}')
                        metadata.append({'document_id': str(doc), 'filename': f'{doc}.pdf', 'chunk_index': chunk, 'page': chunk + 1})
                index.upsert(ids, contents, metadata)
            self.assertEqual(index.count(), 4000)
            matches = index.search('CODE000999', 48)
            self.assertEqual(len(matches), 4)
            self.assertTrue(all(identifier.startswith('999:') for identifier in matches))
            result = index.document_page('999', limit=2, page=4)
            self.assertEqual(result['total'], 4)
            self.assertEqual(result['offset'], 2)
            self.assertEqual([chunk['chunk_index'] for chunk in result['chunks']], [2, 3])
            self.assertTrue(result['target_found'])

    def test_ingestion_batches_and_search_never_fetch_full_corpus(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(_env_file=None, chroma_dir=directory, embedding_batch_size=7,
                                index_page_size=17, min_similarity=0.5, rerank_backend='off')
            with patch('app.rag.vector_store.get_settings', return_value=settings), \
                 patch('app.rag.vector_store.OllamaEmbeddings', ScaleEmbeddings), \
                 patch('app.rag.reranking.get_settings', return_value=settings):
                store = VectorStore()
                try:
                    ScaleEmbeddings.batches = []
                    produced = 0
                    def stream():
                        nonlocal produced
                        for index in range(520):
                            produced += 1
                            # Every completed embedding call consumed at most a single batch ahead.
                            self.assertLessEqual(produced - sum(ScaleEmbeddings.batches), 7)
                            yield Document(page_content=f'Unique code ID{index:05d}', metadata={'page': index // 2 + 1})
                    self.assertEqual(store.add('doc', 'large.pdf', stream()), 520)
                    self.assertLessEqual(max(ScaleEmbeddings.batches), 7)
                    with patch.object(store.collection, 'get', side_effect=AssertionError('Query fetched corpus')):
                        sources = store.search('ID00501', 6, use_rerank=False)
                        result = store.document_page('doc', limit=50, chunk_index=501)
                    self.assertEqual(sources[0]['chunk_index'], 501)
                    self.assertEqual(result['offset'], 500)
                    self.assertEqual(result['total'], 520)
                    self.assertTrue(result['target_found'])
                    self.assertEqual(len(result['chunks']), 20)
                    self.assertIn(501, [chunk['chunk_index'] for chunk in result['chunks']])
                    calls_before = len(ScaleEmbeddings.batches)
                    store.lexical.clear()
                    with patch.object(store.collection, 'get', wraps=store.collection.get) as get:
                        store.rebuild_lexical()
                        self.assertTrue(all(call.kwargs.get('limit') == 17 for call in get.call_args_list))
                    self.assertEqual(len(ScaleEmbeddings.batches), calls_before)
                    self.assertEqual(store.lexical.count(), 520)
                    with self.assertRaises(ValueError):
                        store.add('doc', 'large.pdf', [])
                    self.assertEqual(store.collection.count(), 520)
                finally:
                    store.client._system.stop()

    def test_file_limit_rolls_back_and_does_not_call_embedding(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(_env_file=None, upload_dir=directory, upload_max_file_mb=1, upload_max_request_mb=3)
            db = MagicMock()
            with patch('app.services.document_service.get_settings', return_value=settings), \
                 patch('app.services.document_service.get_vector_store') as store:
                with self.assertRaises(HTTPException) as caught:
                    upload_files([UploadFile(filename='large.pdf', file=io.BytesIO(b'x' * (1024 * 1024 + 1)))], db)
                self.assertEqual(caught.exception.status_code, 413)
                store.assert_not_called()
            self.assertEqual(list(Path(directory).iterdir()), [])
            db.rollback.assert_called_once()

    def test_file_count_limit_prevents_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(_env_file=None, upload_dir=directory, upload_max_files=1)
            with patch('app.services.document_service.get_settings', return_value=settings):
                with self.assertRaises(HTTPException) as caught:
                    upload_files([UploadFile(filename='a.pdf', file=io.BytesIO()), UploadFile(filename='b.pdf', file=io.BytesIO())], MagicMock())
                self.assertEqual(caught.exception.status_code, 400)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_body_limit_for_declared_and_chunked_requests(self):
        app = FastAPI()
        app.add_middleware(UploadBodyLimitMiddleware, max_bytes=10)
        @app.post('/documents/upload')
        async def receive(request: Request):
            return {'bytes': len(await request.body())}
        client = TestClient(app)
        self.assertEqual(client.post('/documents/upload', content=b'x' * 11).status_code, 413)
        response = client.post('/documents/upload', content=iter([b'x' * 6, b'x' * 6]))
        self.assertEqual(response.status_code, 413)
        self.assertEqual(client.post('/documents/upload', content=b'x' * 10).json(), {'bytes': 10})


if __name__ == '__main__':
    unittest.main()
