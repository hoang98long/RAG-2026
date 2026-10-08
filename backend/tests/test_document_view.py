import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from app.core.config import Settings
from app.core.database import get_db
from app.main import app
from app.models.models import Document


class DocumentViewTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.uploads = self.root / 'uploads'
        self.uploads.mkdir()
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        output = io.BytesIO()
        writer.write(output)
        self.pdf = output.getvalue()
        self.file = self.uploads / 'source.pdf'
        self.file.write_bytes(self.pdf)
        self.record = Document(id='source', filename='source.pdf', filepath=str(self.file))
        self.db = MagicMock()
        self.db.get.return_value = self.record
        app.dependency_overrides[get_db] = lambda: self.db
        self.addCleanup(lambda: app.dependency_overrides.pop(get_db, None))
        self.settings = Settings(_env_file=None, upload_dir=str(self.uploads))
        self.client = TestClient(app)

    def test_pdf_served_inline_and_supports_ranges(self):
        with patch('app.api.routes.get_settings', return_value=self.settings):
            response = self.client.get('/documents/source/file')
            partial = self.client.get('/documents/source/file', headers={'Range': 'bytes=0-9'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, self.pdf)
        self.assertEqual(response.headers['content-type'], 'application/pdf')
        self.assertTrue(response.headers['content-disposition'].startswith('inline'))
        self.assertEqual(partial.status_code, 206)
        self.assertEqual(partial.content, self.pdf[:10])

    def test_content_preserves_chunk_and_page_for_source_navigation(self):
        chunks = [{'content': 'Source passage', 'chunk_index': 4, 'page': 3}]
        with patch('app.api.routes.get_settings', return_value=self.settings), \
             patch('app.api.routes.get_vector_store') as store:
            store.return_value.document_page.return_value = {'chunks': chunks, 'total': 5, 'offset': 0, 'limit': 50, 'target_found': None}
            response = self.client.get('/documents/source/content')
            store.return_value.document_page.assert_called_once_with('source', offset=0, limit=50, chunk_index=None, page=None)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data']['chunks'], chunks)
        self.assertEqual(response.json()['data']['file_type'], 'pdf')

    def test_catalogue_is_paginated_and_rejects_unbounded_page_size(self):
        self.db.scalar.return_value = 127
        self.db.scalars.return_value.all.return_value = []
        response = self.client.get('/documents/paged?offset=100&limit=50')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data'], {'items': [], 'total': 127, 'offset': 100, 'limit': 50})
        statement = self.db.scalars.call_args.args[0]
        self.assertEqual(statement._limit_clause.value, 50)
        self.assertEqual(statement._offset_clause.value, 100)
        self.assertEqual(self.client.get('/documents/paged?limit=201').status_code, 422)

    def test_deleted_document_returns_404(self):
        self.db.get.return_value = None
        self.assertEqual(self.client.get('/documents/source/file').status_code, 404)
        self.assertEqual(self.client.get('/documents/source/content').status_code, 404)

    def test_paths_outside_upload_directory_cannot_be_served(self):
        outside = self.root / 'outside.pdf'
        outside.write_bytes(self.pdf)
        self.record.filepath = str(outside)
        with patch('app.api.routes.get_settings', return_value=self.settings):
            self.assertEqual(self.client.get('/documents/source/file').status_code, 404)

    def test_missing_index_returns_404(self):
        with patch('app.api.routes.get_settings', return_value=self.settings), \
             patch('app.api.routes.get_vector_store') as store:
            store.return_value.document_page.return_value = {'chunks': [], 'total': 0}
            self.assertEqual(self.client.get('/documents/source/content').status_code, 404)


if __name__ == '__main__':
    unittest.main()
