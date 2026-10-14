import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from langchain_core.documents import Document
from langchain_core.messages import AIMessage
from app.core.config import Settings
from app.rag.chunking import load_chunks
from app.rag.citations import citations_valid
from app.rag.evidence import QueryPlan, retrieve_evidence
from app.rag.sections import section_key
from app.rag.vector_store import VectorStore
from app.services.rag_service import ABSTAIN, VERIFICATION_UNAVAILABLE, GroundingReview, CitationQuote, _generate
from test_isolation import FakeEmbedding


class EvidenceTests(unittest.TestCase):
    def settings(self, directory, **kwargs):
        return Settings(_env_file=None,chroma_dir=directory,rerank_backend='off',query_expansion=False,**kwargs)

    def test_pdf_appendix_continues_across_pages_and_normalizes_number(self):
        pages=[Document(page_content='Điều 1. Điều kiện\nTham chiếu Phụ lục I.',metadata={'page':61}),
               Document(page_content='Phụ lục I\nBệnh A',metadata={'page':62}),
               Document(page_content='Bệnh B',metadata={'page':63})]
        with patch('app.rag.chunking.PyPDFLoader') as loader:
            loader.return_value.lazy_load.return_value=pages
            chunks=load_chunks(Path('appendix.pdf'))
        self.assertEqual(chunks[-1].metadata['section'],'Phụ lục I')
        self.assertEqual(chunks[-1].metadata['page'],64)
        self.assertEqual(section_key('Phụ lục 01'),section_key('Phụ lục I'))

    def test_complete_appendix_reads_64_rows_with_only_two_display_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            settings=self.settings(directory)
            with patch('app.rag.vector_store.get_settings',return_value=settings), \
                 patch('app.rag.vector_store.OllamaEmbeddings',FakeEmbedding), \
                 patch('app.rag.evidence.get_settings',return_value=settings), \
                 patch('app.rag.reranking.get_settings',return_value=settings):
                store=VectorStore()
                try:
                    chunks=[Document(page_content='Các trường hợp được khám: xem Phụ lục I.',metadata={'section':'Điều 1. Quy định','page':62})]
                    chunks += [Document(page_content=f'Mặt bệnh {index+1}: CODE{index:03d}',metadata={'section':'Phụ lục I','page':63+index//10}) for index in range(64)]
                    store.add('law','regulation.pdf',chunks)
                    result=retrieve_evidence('Liệt kê toàn bộ mặt bệnh tại Phụ lục 01',[store],MagicMock(),'qwen2.5:7b')
                    self.assertGreaterEqual(len(result.evidence),64)
                    self.assertEqual(len(result.sources),2)
                    self.assertFalse(result.coverage['completeness_unverified'])
                    self.assertTrue(set(range(1,65)).issubset({item['chunk_index'] for item in result.evidence}))
                    self.assertEqual(len({item['source_id'] for item in result.evidence}),len(result.evidence))
                    self.assertEqual(len({item['digest'] for item in result.evidence}),len(result.evidence))
                    # A colloquial question reaches the appendix via the rule paragraph,
                    # without an appendix identifier in the user's query.
                    linked=retrieve_evidence('Các trường hợp được khám trực tiếp không cần giấy chuyển',[store],MagicMock(),'qwen2.5:7b')
                    self.assertEqual({item['chunk_index'] for item in linked.evidence},set(range(65)))
                    self.assertFalse(linked.coverage['completeness_unverified'])

                finally: store.client._system.stop()

    def test_section_expansion_reports_truncation_and_preserves_cross_document_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            settings=self.settings(directory,evidence_max_chunks=6,exhaustive_context_chars=2000)
            with patch('app.rag.vector_store.get_settings',return_value=settings), \
                 patch('app.rag.vector_store.OllamaEmbeddings',FakeEmbedding), \
                 patch('app.rag.evidence.get_settings',return_value=settings), \
                 patch('app.rag.reranking.get_settings',return_value=settings):
                store=VectorStore()
                try:
                    store.add('a','A.pdf',[Document(page_content=f'Appendix case {i}',metadata={'section':'Phụ lục I'}) for i in range(20)])
                    store.add('b','B.pdf',[Document(page_content='Quy định áp dụng thêm cho Appendix case',metadata={'section':'Điều 1'})])
                    result=retrieve_evidence('Liệt kê toàn bộ case',[store],MagicMock(),'qwen2.5:7b')
                    self.assertTrue(result.coverage['truncated'])
                    self.assertTrue(result.coverage['completeness_unverified'])
                    self.assertEqual({item['document_id'] for item in result.evidence},{'a','b'})
                    self.assertLessEqual(len(result.evidence),6)
                finally: store.client._system.stop()

    def test_colloquial_query_and_follow_up_search_keep_original_and_model_is_local(self):
        settings=Settings(_env_file=None,rerank_backend='off',query_expansion=True)
        store=MagicMock(scope='private')
        source={'scope':'private','document':'A.pdf','document_id':'a','chunk_index':0,'content':'Quy định chuyển cơ sở khám bệnh','section':'','page':1}
        store.candidates.return_value=[source]
        store.expand.return_value=([source],1)
        llm=MagicMock()
        llm.with_structured_output.return_value.invoke.side_effect=[
            QueryPlan(queries=['điều kiện chuyển cơ sở khám bệnh'],exhaustive=False),
            QueryPlan(queries=['quy định áp dụng danh mục'],exhaustive=False)]
        with patch('app.rag.evidence.get_settings',return_value=settings),patch('app.rag.reranking.get_settings',return_value=settings):
            result=retrieve_evidence('Khám không cần giấy chuyển được không?',[store],llm,'qwen2.5:7b')
        self.assertEqual([call.args[0] for call in store.candidates.call_args_list],
                         ['Khám không cần giấy chuyển được không?','điều kiện chuyển cơ sở khám bệnh','quy định áp dụng danh mục'])
        self.assertEqual(result.coverage['query_count'],3)
        self.assertFalse(result.coverage['query_planning_fallback'])

    def test_missing_requested_appendix_does_not_claim_complete_scope(self):
        settings=Settings(_env_file=None,rerank_backend='off',query_expansion=False)
        store=MagicMock(scope='private')
        source={'scope':'private','document':'A.pdf','document_id':'a','chunk_index':0,
                'content':'General rule','section':'Article 1','page':1}
        store.candidates.return_value=[source]
        store.expand.return_value=([source],1)
        store.related_section.return_value=([],0)
        with patch('app.rag.evidence.get_settings',return_value=settings),patch('app.rag.reranking.get_settings',return_value=settings):
            result=retrieve_evidence('Liệt kê toàn bộ Appendix I',[store],MagicMock(),'qwen2.5:7b')
        self.assertTrue(result.coverage['completeness_unverified'])
        self.assertEqual(result.coverage['missing_referenced_sections'],['private:a:appendix:1'])

    def test_planner_failure_retains_original_query(self):
        settings=Settings(_env_file=None,rerank_backend='off')
        store=MagicMock(scope='public')
        store.candidates.return_value=[]
        llm=MagicMock()
        llm.with_structured_output.return_value.invoke.side_effect=RuntimeError('offline')
        with patch('app.rag.evidence.get_settings',return_value=settings),patch('app.rag.reranking.get_settings',return_value=settings):
            result=retrieve_evidence('Original',[store],llm,'qwen2.5:7b')
        store.candidates.assert_called_once_with('Original')
        self.assertTrue(result.coverage['query_planning_fallback'])

    def test_wrong_content_with_valid_source_id_is_repaired_or_withheld(self):
        source={'source_id':'S1','document':'A.pdf','chunk_index':0,'content':'24 tháng','page':1}
        llm=MagicMock()
        llm.invoke.side_effect=[AIMessage(content='12 tháng [S1]'),AIMessage(content='24 tháng [S1]')]
        llm.with_structured_output.return_value.invoke.side_effect=[GroundingReview(supported=False,issues=['Wrong duration']),GroundingReview(supported=True,issues=[],citations=[CitationQuote(source_id='S1',claim='24 tháng',quote='24 tháng')])]
        text=_generate('Question',[source],llm=llm,verify=True,question='Thời hạn?')
        self.assertEqual(text,'24 tháng [S1]')
        llm.invoke.side_effect=None
        llm.invoke.return_value=AIMessage(content='12 tháng [S1]')
        llm.with_structured_output.return_value.invoke.side_effect=None
        llm.with_structured_output.return_value.invoke.return_value=GroundingReview(supported=False,issues=['Wrong duration'])
        self.assertEqual(_generate('Question',[source],llm=llm,verify=True),ABSTAIN)
        llm.with_structured_output.return_value.invoke.side_effect=RuntimeError('offline')
        self.assertEqual(_generate('Question',[source],llm=llm,verify=True),VERIFICATION_UNAVAILABLE)

    def test_evaluation_cli_can_measure_expanded_evidence_without_answer_generation(self):
        import json
        import io
        from contextlib import redirect_stdout
        from app.evaluate import main
        from app.rag.evidence import EvidenceResult
        with tempfile.TemporaryDirectory() as directory:
            dataset=Path(directory)/'queries.jsonl'
            output=Path(directory)/'report.json'
            dataset.write_text(json.dumps({'question':'Q','expected_sources':[{'document':'A.pdf','chunk_index':63}]}),encoding='utf-8')
            store=MagicMock()
            store.collection.name='test_v5'
            result=EvidenceResult([{'document':'A.pdf','chunk_index':63}],[],{'evidence_chunks':1})
            with patch('app.evaluate.get_vector_store',return_value=store), \
                 patch('app.evaluate._llm'), patch('app.evaluate.retrieve_evidence',return_value=result) as retrieval, \
                 patch('sys.argv',['evaluate',str(dataset),'--expanded','--scope','public','--hybrid-only','--output',str(output)]), \
                 redirect_stdout(io.StringIO()):
                main()
            report=json.loads(output.read_text(encoding='utf-8'))
            self.assertEqual(report['configuration']['evaluation_target'],'full_evidence')
            self.assertEqual(report['summary']['recall_at_k'],1)
            self.assertEqual(report['results'][0]['coverage'],{'evidence_chunks':1})
            self.assertFalse(retrieval.call_args.kwargs['use_rerank'])
            store.search.assert_not_called()

    def test_grouped_citations_validate_every_id(self):
        self.assertTrue(citations_valid('Claim [S1, S2]',[{'source_id':'S1'},{'source_id':'S2'}]))
        self.assertFalse(citations_valid('Claim [S1, S99]',[{'source_id':'S1'}]))


if __name__=='__main__': unittest.main()
