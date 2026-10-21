import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from langchain_core.messages import AIMessage
from app.core.config import Settings
from app.core.database import Base
from app.models.models import Document, ChatHistory
from app.rag.evidence import QueryPlan, retrieve_evidence
from app.rag.reranking import RelevanceBatch, RelevanceGrade
from app.services.rag_service import answer, _review, GroundingReview, CitationQuote
from app.services.source_catalogue import CataloguedStore


def passage(identifier='valid', scope='public', index=0, content='24 months', section=''):
    return dict(scope=scope, document_id=identifier, document=f'{identifier}.pdf',
                content=content, chunk_index=index, section=section, source_id=f'S{index+1}')


class CatalogueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.settings = Settings(_env_file=None, upload_dir=str(self.root/'private'),
            public_upload_dir=str(self.root/'public'), query_expansion=False,
            rerank_backend='off', grounding_verification=False, openai_api_key='test-key')
        self.engine = create_engine('sqlite://')
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)
        for scope in ('private', 'public'):
            (self.root/scope).mkdir()
        self.store = MagicMock(scope='public')
        self.patcher = patch('app.services.source_catalogue.get_settings', return_value=self.settings)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.checked = CataloguedStore(self.store, self.db, 'public')

    def record(self, identifier, scope='public', exists=True):
        path = self.root/scope/f'{identifier}.pdf'
        if exists:
            path.write_bytes(b'fixture')
        self.db.add(Document(id=identifier, filename=f'{identifier}.pdf', filepath=str(path)))
        self.db.commit()

    def test_orphan_missing_file_and_wrong_scope_path_are_removed(self):
        self.record('valid')
        self.record('missing', exists=False)
        self.record('private-file', scope='private')
        self.store.candidates.return_value = [passage(name) for name in ('valid','orphan','missing','private-file')]
        self.assertEqual([item['document_id'] for item in self.checked.candidates('Q')], ['valid'])

    def test_scope_and_filename_must_match_metadata(self):
        self.record('valid')
        self.store.candidates.return_value = [passage(scope='private'),
            {**passage(), 'document':'other.pdf'}, passage()]
        self.assertEqual(self.checked.candidates('Q'), [passage()])

    def test_deleted_source_is_rechecked_before_section_expansion(self):
        self.record('valid')
        self.store.candidates.return_value = [passage()]
        self.assertEqual(len(self.checked.candidates('Q')), 1)
        self.db.delete(self.db.get(Document, 'valid'))
        self.db.commit()
        self.assertEqual(self.checked.expand(passage(), whole_section=True, limit=80), ([],0))
        self.assertEqual(self.checked.related_section(passage(), 'appendix:1',80), ([],0))
        self.store.expand.assert_not_called()
        self.store.related_section.assert_not_called()

    def test_expansion_cannot_introduce_unknown_sources(self):
        self.record('valid')
        self.store.expand.return_value = ([passage(index=1),passage('orphan')],2)
        rows,total = self.checked.expand(passage(),whole_section=True,limit=80)
        self.assertEqual([item['document_id'] for item in rows],['valid'])
        self.assertEqual(total,2)

    def test_catalogue_lookups_are_bounded_and_do_not_scan_the_corpus(self):
        self.record('valid')
        queries = []
        event.listen(self.engine,'before_cursor_execute',lambda connection,cursor,statement,params,context,many: queries.append((statement,params)))
        self.store.candidates.return_value = [passage(str(index)) for index in range(600)]+[passage()]
        self.assertEqual(self.checked.candidates('Q'),[passage()])
        self.assertEqual(len(queries),3)
        self.assertTrue(all('WHERE documents.id IN' in query and len(params)<=256 for query,params in queries))

    def test_openai_filters_before_planning_grading_and_generation_without_private_reads(self):
        self.record('valid')
        self.store.candidates.return_value = [passage(),passage('orphan',content='ORPHAN_CANARY')]
        self.store.expand.side_effect = lambda source,**kwargs: ([source],1)
        private_db, llm = MagicMock(), MagicMock()
        settings = self.settings.model_copy(update={'query_expansion':True, 'rerank_backend':'ollama'})
        planner, grader = MagicMock(), MagicMock()
        planner.invoke.return_value = QueryPlan(queries=[], exhaustive=False)
        grader.invoke.return_value = RelevanceBatch(items=[RelevanceGrade(candidate_id=0,grade=3)])
        llm.with_structured_output.side_effect = lambda schema,**kwargs: planner if schema is QueryPlan else grader
        llm.invoke.return_value = AIMessage(content='24 months [S1]')
        # A real public metadata session is used; no OpenAI network call is made.
        with patch('app.services.rag_service.get_settings',return_value=settings), \
             patch('app.services.model_provider.get_settings',return_value=settings), \
             patch('app.rag.evidence.get_settings',return_value=settings), \
             patch('app.rag.reranking.get_settings',return_value=settings), \
             patch('app.services.rag_service._llm',return_value=llm), \
             patch('app.services.rag_service.get_vector_store',return_value=self.store) as stores, \
             patch('app.services.rag_service.public_session_factory',return_value=lambda:self.db):
            text,sources,_,_=answer('Duration?',private_db,model='openai',scope='public')
        self.assertEqual(text,'24 months [S1]')
        self.assertEqual([item['document_id'] for item in sources],['valid'])
        self.assertNotIn('ORPHAN_CANARY',str(llm.mock_calls)+str(planner.mock_calls)+str(grader.mock_calls))
        self.assertEqual(planner.invoke.call_count,2)
        self.assertEqual(grader.invoke.call_count,1)
        self.assertEqual(private_db.mock_calls,[])
        stores.assert_called_once_with('public')

    def test_evaluation_matches_chat_catalogue_filter_and_only_opens_selected_database(self):
        import io
        import json
        from contextlib import redirect_stdout
        from app.evaluate import main
        self.record('valid')
        self.store.collection.name='fixture_v5'
        self.store.candidates.return_value=[passage(),passage('orphan')]
        self.store.expand.side_effect=lambda source,**kwargs: ([source],1)
        dataset,output=self.root/'cases.jsonl',self.root/'result.json'
        dataset.write_text(json.dumps({'question':'Duration?', 'expected_sources':[{'document_id':'valid'}]}),encoding='utf-8')
        with patch('app.evaluate.get_vector_store',return_value=self.store), \
             patch('app.evaluate.get_settings',return_value=self.settings), \
             patch('app.evaluate.SessionLocal') as private, \
             patch('app.evaluate.public_session_factory',return_value=lambda:self.db), \
             patch('app.evaluate._llm'), \
             patch('app.rag.evidence.get_settings',return_value=self.settings), \
             patch('app.rag.reranking.get_settings',return_value=self.settings), \
             patch('sys.argv',['evaluate',str(dataset),'--scope','public','--expanded','--hybrid-only','--output',str(output)]), \
             redirect_stdout(io.StringIO()):
            main()
        result=json.loads(output.read_text(encoding='utf-8'))
        self.assertTrue(result['configuration']['catalogue_validated'])
        self.assertEqual([item['document_id'] for item in result['results'][0]['sources']],['valid'])
        self.assertEqual(result['summary']['recall_at_k'],1)
        private.assert_not_called()

    def test_report_filters_invalid_sources_before_grading(self):
        self.record('valid',scope='private')
        self.store.scope='private'
        self.store.candidates.return_value=[passage(scope='private'),passage('orphan',scope='private')]
        checked=CataloguedStore(self.store,self.db,'private')
        with patch('app.services.source_catalogue.rerank',side_effect=lambda question,items,**kwargs:items) as grader:
            rows=checked.search('Q',6)
        self.assertEqual([item['document_id'] for item in rows],['valid'])
        self.assertEqual([item['document_id'] for item in grader.call_args.args[1]],['valid'])


class EvidenceSelectionTests(unittest.TestCase):
    def retrieve(self, store, question, **values):
        settings=Settings(_env_file=None,query_expansion=False,rerank_backend='off',**values)
        with patch('app.rag.evidence.get_settings',return_value=settings), \
             patch('app.rag.reranking.get_settings',return_value=settings):
            return retrieve_evidence(question,[store],MagicMock(),'qwen2.5:7b')

    def test_requested_appendix_precedes_long_unrelated_section(self):
        store=MagicMock(scope='public')
        anchor=passage(content='Rule refers to Appendix I.',section='Article 1')
        broad=[{**anchor,'chunk_index':i+1,'content':'x'*1600} for i in range(6)]
        target=passage(index=7,content='Important appendix item',section='Appendix I')
        store.candidates.return_value=[anchor]
        store.expand.return_value=([anchor]+broad,7)
        store.related_section.return_value=([target],1)
        result=self.retrieve(store,'Li\u1ec7t k\u00ea cases in Appendix I',exhaustive_context_chars=2000)
        self.assertTrue(result.coverage['exhaustive_requested'])
        self.assertIn(7,[item['chunk_index'] for item in result.evidence])
        self.assertEqual(result.coverage['section_retained']['public:valid:appendix:1'],1)

    def test_missing_reference_warns_even_without_exhaustive_request(self):
        store=MagicMock(scope='public')
        anchor=passage(content='See Appendix I.',section='Article 1')
        store.candidates.return_value=[anchor]
        store.expand.return_value=([anchor],1)
        store.related_section.return_value=([],0)
        result=self.retrieve(store,'What is the condition?')
        self.assertFalse(result.coverage['exhaustive_requested'])
        self.assertTrue(result.coverage['completeness_unverified'])

    def test_reference_exists_but_is_not_fully_retained_in_context(self):
        store=MagicMock(scope='public')
        anchor=passage(content='See Appendix I.',section='Article 1')
        rows=[passage(index=i+1,content='x'*950,section='Appendix I') for i in range(4)]
        store.candidates.return_value=[anchor]
        store.expand.return_value=([anchor],1)
        store.related_section.return_value=(rows,4)
        result=self.retrieve(store,'Conditions?',chunk_size=200,chunk_overlap=20,max_context_chars=2000)
        self.assertTrue(result.coverage['completeness_unverified'])
        self.assertEqual(result.coverage['incomplete_referenced_sections'],['public:valid:appendix:1'])
        self.assertLess(result.coverage['section_retained']['public:valid:appendix:1'],4)

    def test_quote_for_another_cited_line_cannot_validate_a_source(self):
        sources=[passage(index=0,content='24 months'),passage(index=1,content='48 months')]
        text='48 months [S1]\n24 months [S2]'
        llm=MagicMock()
        llm.with_structured_output.return_value.invoke.return_value=GroundingReview(supported=True,issues=[],citations=[
            CitationQuote(source_id='S1',claim='24 months',quote='24 months'),
            CitationQuote(source_id='S2',claim='48 months',quote='48 months')])
        self.assertFalse(_review(llm,text,sources).supported)

    def test_each_cited_line_needs_its_own_evidence_quote(self):
        llm=MagicMock()
        llm.with_structured_output.return_value.invoke.return_value=GroundingReview(supported=True,issues=[],citations=[
            CitationQuote(source_id='S1',claim='24 months',quote='24 months')])
        self.assertFalse(_review(llm,'24 months [S1]\n48 months [S1]',[passage(content='24 months')]).supported)


if __name__=='__main__': unittest.main()
