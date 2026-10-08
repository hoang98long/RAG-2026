import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from fastapi import HTTPException, UploadFile
from fastapi.testclient import TestClient
from langchain_core.documents import Document
from pypdf import PdfWriter
from app.core.config import Settings
from app.core.database import get_db
from app.main import app
from app.services.document_service import upload_files


class UploadTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.settings = Settings(_env_file=None, upload_dir=self.directory.name)
        self.db = MagicMock()

    def pdf_bytes(self, encrypted=False):
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        if encrypted:
            writer.encrypt('secret')
        output = io.BytesIO()
        writer.write(output)
        return output.getvalue()

    def check_rejected_pdf(self, data, expected):
        app.dependency_overrides[get_db] = lambda: self.db
        try:
            with patch('app.services.document_service.get_settings', return_value=self.settings), \
                 patch('app.services.document_service.get_vector_store') as store:
                response = TestClient(app).post('/documents/upload', files={'files': ('56-bqp.pdf', data, 'application/pdf')})
                self.assertEqual(response.status_code, 400)
                self.assertIn(expected, response.json()['detail'])
                self.assertIn('56-bqp.pdf', response.json()['detail'])
                store.assert_not_called()
        finally:
            app.dependency_overrides.pop(get_db, None)
        self.db.rollback.assert_called_once()
        self.db.commit.assert_not_called()
        self.assertEqual(list(Path(self.directory.name).iterdir()), [])

    def test_pdf_without_text_returns_ocr_guidance(self):
        self.check_rejected_pdf(self.pdf_bytes(), 'OCR')

    def test_encrypted_pdf_returns_readable_error(self):
        self.check_rejected_pdf(self.pdf_bytes(encrypted=True), 'mật khẩu')

    def test_corrupt_pdf_returns_readable_error(self):
        self.check_rejected_pdf(b'%PDF-broken', 'không đọc được tệp')

    def test_success_uses_embedding_without_chat_llm(self):
        chunks = [Document(page_content='Nội dung tài liệu', metadata={'page': 1})]
        with patch('app.services.document_service.get_settings', return_value=self.settings), \
             patch('app.services.document_service.load_chunks', return_value=chunks), \
             patch('app.services.document_service.get_vector_store') as store, \
             patch('app.services.rag_service._llm') as llm:
            records = upload_files([UploadFile(filename='document.pdf', file=io.BytesIO(b'pdf'))], self.db)
            store.return_value.add.assert_called_once_with(records[0].id, 'document.pdf', chunks)
            llm.assert_not_called()
        self.db.commit.assert_called_once()
        self.assertTrue(Path(records[0].filepath).is_file())

    def test_partial_embedding_failure_cleans_uploaded_file_and_vectors(self):
        with patch('app.services.document_service.get_settings', return_value=self.settings), \
             patch('app.services.document_service.load_chunks', return_value=[Document(page_content='Text')]), \
             patch('app.services.document_service.get_vector_store') as store:
            store.return_value.add.side_effect = RuntimeError('embedding failed')
            with self.assertRaises(RuntimeError):
                upload_files([UploadFile(filename='document.pdf', file=io.BytesIO(b'pdf'))], self.db)
            store.return_value.delete_document.assert_called_once()
        self.db.rollback.assert_called_once()
        self.assertEqual(list(Path(self.directory.name).iterdir()), [])


if __name__ == '__main__':
    unittest.main()
