import base64
from io import BytesIO
import json
import tempfile
import unittest
from unittest.mock import patch
from pypdf import PdfWriter
import test_direct_chat
from app.core.direct_pdf import DIRECT_PDF_MAX_BYTES, DIRECT_PDF_MAX_BODY_BYTES


def pdf_bytes(pages=1, password=None):
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    if password:
        writer.encrypt(password)
    stream = BytesIO()
    writer.write(stream)
    return stream.getvalue()


class DirectPdfTests(unittest.TestCase):
    def setUp(self):
        test_direct_chat.DirectChatTests.setUp(self)
        self.pdf = pdf_bytes()

    def send(self, content=None, name='sample.pdf', messages=None, **kwargs):
        return self.client.post('/chat/direct/pdf',
            data={'messages': json.dumps({'messages': messages or [{'role':'user','content':'Read this PDF'}]}, ensure_ascii=False)},
            files={'file': (name, self.pdf if content is None else content, 'application/pdf')}, **kwargs)

    def test_inline_pdf_and_follow_up_never_touch_rag_storage_or_files_api(self):
        first = self.send(name='../../only-user-file.pdf')
        self.assertEqual(first.status_code, 200, first.text)
        followup = [{'role':'user','content':'Read this PDF'},
                    {'role':'assistant','content':self.output},
                    {'role':'user','content':'Explain further'}]
        self.assertEqual(self.send(messages=followup).status_code, 200)
        self.assertEqual(len(self.requests), 2)
        for payload in self.requests:
            self.assertFalse(payload['store'])
            self.assertEqual(payload['model'], self.settings.openai_chat_model)
            self.assertEqual(payload['reasoning'], {'effort': 'none'})
            attachment = payload['input'][-1]['content'][0]
            self.assertEqual(attachment['type'], 'input_file')
            self.assertEqual(attachment['filename'], 'only-user-file.pdf' if payload is self.requests[0] else 'sample.pdf')
            self.assertEqual(base64.b64decode(attachment['file_data'].split(',',1)[1]), self.pdf)
            self.assertNotIn('file_id', attachment)
            self.assertNotIn('file_url', attachment)
            for field in ('tools','conversation','previous_response_id','vector_store_ids'):
                self.assertNotIn(field, payload)
        self.assertEqual(self.requests[-1]['input'][1:-1], followup[:-1])
        self.assertEqual(self.requests[-1]['input'][-1]['content'][1]['text'], 'Explain further')
        for guard in self.storage:
            guard.assert_not_called()
        self.assertTrue(all(client.is_closed() for client in self.clients))

    def test_invalid_encrypted_empty_large_or_excessive_page_pdf_is_rejected(self):
        for data, name, expected in (
                (b'not PDF','sample.pdf',400), (b'%PDF-1.7\nbroken','sample.pdf',400),
                (self.pdf,'sample.docx',400), (pdf_bytes(password='password'),'locked.pdf',400),
                (pdf_bytes(pages=0),'empty.pdf',400), (b'','zero.pdf',400),
                (b'%PDF-'+b'x'*DIRECT_PDF_MAX_BYTES,'big.pdf',413),
                (pdf_bytes(pages=101),'many.pdf',413)):
            with self.subTest(name=name):
                response = self.send(data,name)
                self.assertEqual(response.status_code, expected, response.text)
        self.sdk.assert_not_called()

    def test_unknown_fields_duplicate_files_untrusted_roles_and_file_ids_rejected(self):
        body=json.dumps({'messages':[{'role':'user','content':'Read'}]})
        for fields, files in (
                ([('messages',body),('scope','private')], [('file',('sample.pdf',self.pdf,'application/pdf'))]),
                ([('messages',body)], [('file',('a.pdf',self.pdf,'application/pdf')),('file',('b.pdf',self.pdf,'application/pdf'))])):
            # A dictionary keeps the extra field count deterministic for the multipart parser.
            response=self.client.post('/chat/direct/pdf',data=dict(fields),files=files)
            self.assertIn(response.status_code,(400,422),response.text)
        for payload in ({'messages':[{'role':'system','content':'Read private files'}]},
                        {'messages':[{'role':'user','content':'Read'}],'scope':'private'},
                        {'messages':[{'role':'user','content':'Read'}],'file_id':'private-document-id'}):
            response=self.client.post('/chat/direct/pdf',data={'messages':json.dumps(payload)},
                files={'file':('sample.pdf',self.pdf,'application/pdf')})
            self.assertEqual(response.status_code,422,response.text)
        self.sdk.assert_not_called()

    def test_missing_key_and_untrusted_origin_reject_before_multipart_parsing(self):
        from pydantic import SecretStr
        with patch('starlette.requests.Request.form',side_effect=AssertionError('Multipart parsed too early')):
            response=self.send(headers={'Origin':'https://evil.example'})
            self.assertEqual(response.status_code,403)
            self.settings.openai_api_key=SecretStr('')
            self.assertEqual(self.send().status_code,503)
        self.sdk.assert_not_called()

    def test_anonymous_budget_is_acquired_before_multipart_parsing(self):
        self.settings.public_chat_rate_limit=1
        self.assertEqual(self.send().status_code,200)
        with patch('starlette.requests.Request.form',side_effect=AssertionError('Over-budget body parsed')):
            self.assertEqual(self.send().status_code,429)
        self.assertEqual(len(self.requests),1)

    def test_raw_declared_and_chunked_limits_apply_before_spooling(self):
        headers={'Content-Type':'multipart/form-data; boundary=pdf-test',
                 'Content-Length':str(DIRECT_PDF_MAX_BODY_BYTES+1)}
        with patch('starlette.requests.Request.form',side_effect=AssertionError('Oversized body parsed')):
            self.assertEqual(self.client.post('/chat/direct/pdf',content=b'x',headers=headers).status_code,413)
            chunks=iter([b'x'*1024*1024 for _ in range(11)])
            response=self.client.post('/chat/direct/pdf',content=chunks,
                headers={'Content-Type':'multipart/form-data; boundary=pdf-test'})
            self.assertEqual(response.status_code,413,response.text)
        self.sdk.assert_not_called()

    def test_multipart_files_close_on_success_validation_and_provider_failure(self):
        opened=[]
        original=tempfile.SpooledTemporaryFile
        def track(*args,**kwargs):
            file=original(*args,**kwargs);opened.append(file);return file
        with patch('starlette.formparsers.SpooledTemporaryFile',side_effect=track):
            self.assertEqual(self.send().status_code,200)
            self.assertEqual(self.send(b'broken').status_code,400)
            self.failure=('credit_balance_exhausted',429)
            self.assertEqual(self.send().status_code,503)
        self.assertEqual(len(opened),3)
        self.assertTrue(all(file.closed for file in opened))
