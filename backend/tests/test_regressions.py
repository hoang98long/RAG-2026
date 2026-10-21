import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import httpx
from fastapi.testclient import TestClient
from auth_helpers import internal_client
from langchain_core.messages import AIMessage
from ollama import ResponseError
from pydantic import ValidationError
from app.core.config import Settings
from app.core.database import get_db
from app.main import app
from app.rag.citations import quote_support_valid
from app.rag.evidence import QueryPlan, retrieve_evidence
from app.rag.retrieval import fuse_rankings
from app.schemas.schemas import ChatRequest
from app.services.rag_service import CitationQuote, GroundingReview, _review, _context


def source(document='a', index=0, content='Bảo hành 24 tháng', section='', scope='private'):
    return {'scope':scope,'document':f'{document}.pdf','document_id':document,'chunk_index':index,'content':content,'section':section,'source_id':f'S{index+1}','page':1}


class RegressionTests(unittest.TestCase):
    def test_fusion_weights_and_expansion_cannot_outvote_the_original_question(self):
        settings=Settings(_env_file=None,rerank_backend='off')
        store=MagicMock(scope='private')
        good,bad=source(),source('b',content='Other facts')
        store.candidates.side_effect=lambda query:[good] if query=='Original' else [bad]
        store.expand.side_effect=lambda item,**kwargs:([item],1)
        store.related_section.return_value=([],0)
        llm=MagicMock()
        llm.with_structured_output.return_value.invoke.side_effect=[
            QueryPlan(queries=['alternative a','alternative b','alternative c'],exhaustive=False),
            QueryPlan(queries=['follow a','follow b'],exhaustive=False)]
        with patch('app.rag.evidence.get_settings',return_value=settings),patch('app.rag.evidence.rerank',side_effect=lambda query,items,**kwargs:items) as grader:
            result=retrieve_evidence('Original',[store],llm,'qwen2.5:7b')
        self.assertEqual(result.evidence[0]['document_id'],'a')
        self.assertEqual(grader.call_args.args[0],'Original')
        self.assertEqual(result.coverage['query_count'],6)
        self.assertEqual(fuse_rankings(['a'],['b'],weights=[2,1])[0][0],'a')
        with self.assertRaises(ValueError):fuse_rankings(['a'],weights=[])

    def test_rewrites_cannot_invent_numbers_or_appendix_identifiers(self):
        settings=Settings(_env_file=None,rerank_backend='off')
        store=MagicMock(scope='private')
        item=source(section='Phụ lục I')
        store.candidates.return_value=[item]
        store.expand.return_value=([item],1)
        store.related_section.return_value=([item],1)
        llm=MagicMock()
        llm.with_structured_output.return_value.invoke.side_effect=[
            QueryPlan(queries=['Thông tư 999','Phụ lục II','điều kiện bảo hành'],exhaustive=False),
            QueryPlan(queries=['bảo hành 24 tháng','Phụ lục 01'],exhaustive=False)]
        with patch('app.rag.evidence.get_settings',return_value=settings),patch('app.rag.reranking.get_settings',return_value=settings):
            result=retrieve_evidence('Điều kiện bảo hành',[store],llm,'qwen2.5:7b')
        queries=[call.args[0] for call in store.candidates.call_args_list]
        self.assertNotIn('Thông tư 999',queries)
        self.assertNotIn('Phụ lục II',queries)
        self.assertIn('bảo hành 24 tháng',queries)
        self.assertIn('Phụ lục 01',queries)
        self.assertEqual(result.coverage['discarded_queries'],2)

    def test_a_reference_in_document_b_is_not_satisfied_by_document_a(self):
        settings=Settings(_env_file=None,rerank_backend='off',query_expansion=False)
        store=MagicMock(scope='private')
        a=source('a',content='Xem Phụ lục I',section='Điều 1')
        b=source('b',content='Xem Phụ lục I',section='Điều 1')
        store.candidates.return_value=[a,b]
        store.expand.side_effect=lambda item,**kwargs:([item],1)
        store.related_section.side_effect=lambda item,key,limit:([source('a',index=1,section='Phụ lục I')],1) if item['document_id']=='a' else ([],0)
        with patch('app.rag.evidence.get_settings',return_value=settings),patch('app.rag.reranking.get_settings',return_value=settings):
            result=retrieve_evidence('Liệt kê toàn bộ các trường hợp',[store],MagicMock(),'qwen2.5:7b')
        self.assertTrue(result.coverage['completeness_unverified'])
        self.assertEqual(result.coverage['missing_referenced_sections'],['private:b:appendix:1'])

    def test_verifier_cannot_accept_fabricated_quotes_or_missing_quotes(self):
        item=source()
        text='Bảo hành 24 tháng [S1]'
        for proof in [None,CitationQuote(source_id='S1',claim='24 tháng',quote='12 tháng'),
                      CitationQuote(source_id='S99',claim='24 tháng',quote='24 tháng'),
                      CitationQuote(source_id='S1',claim='48 tháng',quote='24 tháng')]:
            llm=MagicMock()
            llm.with_structured_output.return_value.invoke.return_value=GroundingReview(supported=True,issues=[],citations=[proof] if proof else [])
            self.assertFalse(_review(llm,text,[item]).supported)
        self.assertTrue(quote_support_valid('24 tháng','24 tháng',text,item['content']))
        self.assertFalse(quote_support_valid('24 tháng','12 tháng',text,item['content']))

    def test_quote_verification_batches_every_cited_source(self):
        settings=Settings(_env_file=None,review_batch_size=2)
        items=[source(index=index,content=f'Bảo hành {24+index} tháng') for index in range(3)]
        text='\n'.join(f'Bảo hành {24+index} tháng [S{index+1}]' for index in range(3))
        proofs=[CitationQuote(source_id=f'S{index+1}',claim=f'{24+index} tháng',quote=f'{24+index} tháng') for index in range(3)]
        llm=MagicMock()
        llm.with_structured_output.return_value.invoke.side_effect=[
            GroundingReview(supported=True,issues=[],citations=proofs[:2]),GroundingReview(supported=True,issues=[],citations=proofs[2:])]
        with patch('app.services.rag_service.get_settings',return_value=settings):
            review=_review(llm,text,items)
        self.assertTrue(review.supported)
        self.assertEqual(len(review.citations),3)
        self.assertEqual(llm.with_structured_output.return_value.invoke.call_count,2)

    def test_context_retains_source_ids_but_orders_chunks_inside_a_document(self):
        items=[source(index=2,content='Third'),source(index=0,content='First'),source(index=1,content='Second')]
        context=_context(items)
        self.assertLess(context.index('First'),context.index('Second'))
        self.assertLess(context.index('Second'),context.index('Third'))
        self.assertIn('[S3]',context)

    def test_blank_questions_rejected_and_trimmed_question_is_preserved(self):
        with self.assertRaises(ValidationError):ChatRequest(question='   ')
        self.assertEqual(ChatRequest(question='  text  ').question,'text')

    def test_connection_timeout_and_missing_model_are_safe_http_errors(self):
        app.dependency_overrides[get_db]=lambda:MagicMock()
        self.addCleanup(app.dependency_overrides.clear)
        client=internal_client(self, app)
        for error,status in [(httpx.ReadTimeout('PRIVATE_SECRET'),504),(ConnectionError('PRIVATE_SECRET'),503),
                             (ResponseError('PRIVATE_SECRET',status_code=404),503)]:
            with patch('app.api.routes.answer',side_effect=error):
                response=client.post('/chat',json={'question':'Q'})
            self.assertEqual(response.status_code,status)
            self.assertNotIn('PRIVATE_SECRET',response.text)
            self.assertIsInstance(response.json()['detail'],str)


if __name__=='__main__':unittest.main()
