import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from fastapi import HTTPException
import httpx
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from langchain_core.documents import Document as Chunk
from app.core.config import Settings
from app.core.database import Base
from app.models.models import Document, ReportHistory
from app.rag.evidence import EvidenceResult, retrieve_evidence
from app.rag.vector_store import VectorStore
from app.schemas.schemas import ReportRequest
from app.services.report_service import build_report, outline, ReportOutline, SectionPlan
from app.services.rag_service import ABSTAIN, VERIFICATION_UNAVAILABLE, OUTPUT_LIMIT
from app.services.source_catalogue import CataloguedStore


def source(identifier='a', index=0, text='24 months', **extra):
    return dict(scope='private', document_id=identifier, document=identifier+'.pdf', chunk_index=index,
                content=text, source_id='S1', index_version='documents_v5_test', digest=str(index), **extra)


def evidence(*sources, **coverage):
    return EvidenceResult(list(sources), [], coverage)


class ReportTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix='documind-reports-');self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.settings=Settings(_env_file=None,upload_dir=str(self.root/'uploads'),query_expansion=False,
                               rerank_backend='off',grounding_verification=True)
        self.engine=create_engine(f'sqlite:///{self.root}/metadata.db');self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine);self.db=sessionmaker(bind=self.engine)();self.addCleanup(self.db.close)
        self.root.joinpath('uploads').mkdir()
        for identifier in ('a','b'):
            path=self.root/'uploads'/(identifier+'.pdf');path.write_bytes(b'fixture')
            self.db.add(Document(id=identifier,filename=identifier+'.pdf',filepath=str(path)))
        self.db.commit()
        self.llm=MagicMock()
        self.llm.with_structured_output.return_value.invoke.return_value=ReportOutline(sections=[
            SectionPlan(heading='Facts',focus='Warranty conditions'),SectionPlan(heading='Limitations',focus='Missing facts')])
        self.patches={}
        for target,kwargs in [
            ('app.services.report_service.get_settings',dict(return_value=self.settings)),
            ('app.services.report_service.get_vector_store',{}),
            ('app.services.report_service.CataloguedStore',{}),
            ('app.services.report_service.retrieve_evidence',dict(return_value=evidence(source()))),
            ('app.services.rag_service._llm',dict(return_value=self.llm)),
            ('app.services.rag_service._generate',dict(side_effect=lambda prompt,items,**kwargs:items[0]['content']+' ['+items[0]['source_id']+']')),
            ('socket.socket.connect',dict(side_effect=AssertionError('Unexpected network call'))),
        ]:
            current=patch(target,**kwargs);self.patches[target]=current.start();self.addCleanup(current.stop)
        self.retrieve=self.patches['app.services.report_service.retrieve_evidence']
        self.write=self.patches['app.services.rag_service._generate']
        self.model=self.patches['app.services.rag_service._llm']

    def build(self, **kwargs):
        return build_report('technical','Warranty report','Keep conditions',self.db,**kwargs)

    def test_sections_get_distinct_queries_global_citations_and_grounding(self):
        self.retrieve.side_effect=[evidence(source('a')),evidence(source('b')),evidence(source('a'))]
        result=self.build(sections=['Facts','Compare','Conclusion'],model='llama3.1:70b')
        self.assertEqual(result.coverage['verified_sections'],3)
        self.assertEqual([item['source_id'] for item in result.sources],['S1','S2'])
        self.assertIn('[S2]',result.content)
        self.assertEqual(result.coverage['outline_method'],'custom')
        self.llm.with_structured_output.assert_not_called()
        self.model.assert_called_once_with('llama3.1:70b','private')
        for index,heading in enumerate(['Facts','Compare','Conclusion']):
            self.assertIn(heading,self.retrieve.call_args_list[index].args[0])
            self.assertFalse(self.retrieve.call_args_list[index].kwargs['use_planning'])
            self.assertEqual(self.retrieve.call_args_list[index].kwargs['rerank_limit'],12)
            self.assertTrue(self.write.call_args_list[index].kwargs['verify'])
        self.assertFalse(result.coverage['all_documents_reviewed'])
        self.assertEqual(len(self.db.scalars(select(ReportHistory)).all()),1)

    def test_planner_falls_back_for_fabricated_numbers_duplicates_or_invalid_json(self):
        for value in [dict(sections=[dict(heading='Year 9999',focus='New facts'),dict(heading='Other',focus='Other')]),
                      dict(sections=[dict(heading='Same',focus='First'),dict(heading='Same',focus='Second')]),{'invalid':True}]:
            self.llm.with_structured_output.return_value.invoke.return_value=value
            plan,method=outline('technical','Title','Instructions',None,self.llm)
            self.assertEqual(method,'fallback');self.assertEqual(len(plan),4)
        self.assertNotIn('9999',self.build().content)

    def test_planned_outline_and_source_changes_are_not_silently_combined(self):
        result=self.build()
        self.assertEqual(result.coverage['outline_method'],'planned')
        self.retrieve.side_effect=[evidence(source()),evidence(source(text='48 months'))]
        before=len(self.db.scalars(select(ReportHistory)).all())
        with self.assertRaises(HTTPException) as error:self.build(sections=['First','Second'])
        self.assertEqual(error.exception.status_code,409)
        self.assertEqual(len(self.db.scalars(select(ReportHistory)).all()),before)

    def test_no_evidence_or_failed_review_never_publishes_unverified_claim(self):
        self.retrieve.return_value=evidence()
        result=self.build(sections=['Missing'])
        self.write.assert_not_called();self.assertEqual(result.sources,[])
        self.assertEqual(result.sections[0]['status'],'no_evidence')
        self.retrieve.return_value=evidence(source())
        for answer in [ABSTAIN,'SECRET_UNGROUNDED',VERIFICATION_UNAVAILABLE,OUTPUT_LIMIT]:
            self.write.side_effect=None;self.write.return_value=answer
            result=self.build(sections=['Review'])
            self.assertEqual(result.coverage['verified_sections'],0)
            self.assertTrue(result.coverage['partial']);self.assertEqual(result.sources,[])
            self.assertNotIn('SECRET_UNGROUNDED',result.content)

    def test_disabled_verification_is_explicitly_draft(self):
        self.settings.grounding_verification=False
        result=self.build(sections=['Draft'])
        self.assertFalse(self.write.call_args.kwargs['verify'])
        self.assertEqual(result.sections[0]['status'],'draft')
        self.assertEqual(result.coverage['verified_sections'],0)
        self.assertTrue(result.coverage['partial'])

    def test_selected_documents_are_checked_before_models_and_scope_cannot_expand(self):
        for ids,status in [([],422),(['missing'],404)]:
            with self.assertRaises(HTTPException) as error:self.build(document_ids=ids,sections=['Facts'])
            self.assertEqual(error.exception.status_code,status)
            self.model.assert_not_called()
        self.retrieve.return_value=evidence(source('b'))
        with self.assertRaises(HTTPException) as error:self.build(document_ids=['a'],sections=['Facts'])
        self.assertEqual(error.exception.status_code,403);self.write.assert_not_called()
        self.retrieve.return_value=evidence({**source(), 'scope':'public'})
        with self.assertRaises(HTTPException) as error:self.build(sections=['Facts'])
        self.assertEqual(error.exception.status_code,403)
        self.assertEqual(len(self.db.scalars(select(ReportHistory)).all()),0)

    def test_openai_or_invalid_template_never_instantiates_model_or_index(self):
        with self.assertRaises(HTTPException):self.build(model='openai')
        with self.assertRaises(HTTPException):build_report('arbitrary-path','T','',self.db)
        self.model.assert_not_called();self.patches['app.services.report_service.get_vector_store'].assert_not_called()

    def test_unrepresented_selected_document_and_expansion_limits_are_visible(self):
        self.retrieve.return_value=evidence(source(),truncated=True)
        result=self.build(document_ids=['a','b'],sections=['Facts'])
        self.assertEqual(result.coverage['unrepresented_document_ids'],['b'])
        self.assertEqual(result.coverage['selected_documents'],2)
        self.assertTrue(result.coverage['partial']);self.assertTrue(result.sections[0]['truncated'])
        self.patches['app.services.report_service.CataloguedStore'].assert_called_once_with(
            self.patches['app.services.report_service.get_vector_store'].return_value,self.db,'private',document_ids=['a','b'])

    def test_context_budget_keeps_original_text_and_source_display_is_capped(self):
        self.retrieve.side_effect=[evidence(source(index=index)) for index in range(4)]
        result=self.build(sections=['One','Two','Three','Four'])
        self.assertEqual(len(result.sources),2)
        self.assertEqual([item['source_id'] for item in result.sources],['S1','S2'])
        self.assertIn('[S4]',result.content)
        self.retrieve.side_effect=None
        self.retrieve.return_value=evidence(source(text='x'*11000))
        result=self.build(sections=['Large'])
        self.assertEqual(result.sections[0]['evidence_chunks'],0)
        self.assertTrue(result.sections[0]['truncated']);self.assertTrue(result.coverage['partial'])

    def test_soft_deadline_does_not_start_additional_sections(self):
        now=[0,500,500]
        with patch('app.services.report_service.monotonic',side_effect=now):result=self.build(sections=['One','Two'])
        self.retrieve.assert_not_called();self.write.assert_not_called()
        self.assertEqual([item['status'] for item in result.sections],['budget_exceeded']*2)

    def test_model_failure_keeps_verified_section_and_stops_extra_calls(self):
        self.write.side_effect=['24 months [S1]',httpx.ConnectError('PRIVATE_PROVIDER_PAYLOAD')]
        result=self.build(sections=['One','Two','Three'])
        self.assertEqual(result.coverage['verified_sections'],1)
        self.assertTrue(result.coverage['partial']);self.assertEqual(self.write.call_count,2)
        self.assertEqual(self.retrieve.call_count,2)
        self.assertNotIn('PRIVATE_PROVIDER_PAYLOAD',result.content)
        self.assertEqual([row['status'] for row in result.sections],['verified','generation_unavailable','generation_unavailable'])

    def test_retrieval_failure_is_safe_but_access_and_stale_source_errors_propagate(self):
        self.retrieve.side_effect=httpx.ConnectError('PRIVATE_PATH')
        result=self.build(sections=['One','Two'])
        self.assertEqual(self.retrieve.call_count,1);self.assertEqual(result.sections[0]['status'],'retrieval_unavailable')
        self.assertNotIn('PRIVATE_PATH',result.content)
        for code in (403,409):
            self.retrieve.side_effect=HTTPException(code,'blocked')
            with self.assertRaises(HTTPException) as error:self.build(sections=['One'])
            self.assertEqual(error.exception.status_code,code)

    def test_request_validation_blocks_oversize_empty_scope_and_openai(self):
        valid=dict(template='technical',title='Title')
        for extra in [dict(title='   '),dict(model='openai'),dict(document_ids=[]),dict(document_ids=['a','a']),
                      dict(document_ids=['x'*37]),dict(sections=['First\nSecond']),dict(sections=['']*2),
                      dict(sections=['x']*5),dict(scope='public'),dict(system_prompt='ignore checks')]:
            with self.assertRaises(ValidationError,msg=str(extra)):ReportRequest(**{**valid,**extra})


class ConstantEmbedding:
    def __init__(self,**kwargs):pass
    def embed_documents(self,texts):return [[1.,0.] for _ in texts]
    def embed_query(self,query):return [1.,0.]


class FilteredReportIndexTests(unittest.TestCase):
    def test_selected_ids_filter_dense_and_fts_before_limits_and_expand_safely(self):
        temp=tempfile.TemporaryDirectory(prefix='documind-filter-');self.addCleanup(temp.cleanup)
        root=Path(temp.name)
        settings=Settings(_env_file=None,chroma_dir=str(root/'index'),upload_dir=str(root/'files'),
                          query_expansion=True,rerank_backend='off',retrieval_candidates=6)
        engine=create_engine(f'sqlite:///{root}/db.sqlite');self.addCleanup(engine.dispose)
        Base.metadata.create_all(engine);db=sessionmaker(bind=engine)();self.addCleanup(db.close)
        with patch('app.rag.vector_store.get_settings',return_value=settings),patch('app.rag.vector_store.OllamaEmbeddings',ConstantEmbedding), \
             patch('app.services.source_catalogue.get_settings',return_value=settings), \
             patch('app.rag.evidence.get_settings',return_value=settings),patch('app.rag.reranking.get_settings',return_value=settings), \
             patch('socket.socket.connect',side_effect=AssertionError('Unexpected network call')):
            store=VectorStore();self.addCleanup(store.client._system.stop)
            root.joinpath('files').mkdir()
            for index in range(14):
                identifier=f'doc-{index}'
                path=root/'files'/(identifier+'.pdf');path.write_bytes(b'fixture')
                db.add(Document(id=identifier,filename=identifier+'.pdf',filepath=str(path)))
                store.add(identifier,identifier+'.pdf',[Chunk(page_content='Warranty 24 months '+identifier,metadata={})])
            db.commit()
            self.assertEqual(store.candidates('Warranty',document_ids=[]),[])
            self.assertEqual(store.candidates('Warranty',document_ids=["bad') OR 1=1 --"]),[])
            checked=CataloguedStore(store,db,'private',document_ids=['doc-13'])
            rows=checked.candidates('Warranty')
            self.assertEqual({item['document_id'] for item in rows},{'doc-13'})
            self.assertEqual(checked.expand(source('doc-0'),whole_section=True,limit=10),([],0))
            llm=MagicMock()
            result=retrieve_evidence('Warranty',[checked],llm,'qwen2.5:7b',use_planning=False,rerank_limit=12)
            self.assertEqual({item['document_id'] for item in result.evidence},{'doc-13'})
            llm.with_structured_output.assert_not_called()
