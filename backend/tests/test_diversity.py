import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch
from pydantic import ValidationError
from fastapi import HTTPException
from app.core.config import Settings
from app.evaluate import main, retrieval_metrics
from app.rag.diversity import interleave_sections, mmr_pool
from app.rag.evidence import retrieve_evidence
from app.rag.reranking import RelevanceBatch, RelevanceGrade, rerank


def passage(document='a', index=0, content='Repeated warranty clause applies to equipment.', section='', scope='private'):
    return {'scope':scope,'document_id':document,'document':f'{document}.pdf','chunk_index':index,
            'content':content,'section':section}


class DiversityTests(unittest.TestCase):
    def test_mmr_admits_complementary_evidence_beyond_the_old_top_32(self):
        items=[passage(index=index) for index in range(40)]
        target=passage('b',content='Eligibility requires an independent inspection certificate.')
        items.append(target)
        selected=mmr_pool(items,32)
        self.assertIn(target,selected)
        self.assertNotIn(target,items[:32])
        self.assertEqual(len(selected),32)
        self.assertEqual(selected[:8],items[:8])
        self.assertEqual([items.index(item) for item in selected],sorted(items.index(item) for item in selected))
        self.assertEqual(items[-1],target)

    def test_short_pool_preserves_numeric_negative_and_scope_variants(self):
        items=[passage(content='Warranty 24 months.'),passage(index=1,content='Warranty 12 months.'),
               passage(index=2,content='Warranty does not apply.'),passage(scope='public')]
        self.assertEqual(mmr_pool(items,32),items)
        self.assertEqual(len(mmr_pool(items,32)),4)

    def test_mmr_keeps_distinct_numeric_and_negative_clauses_in_a_large_pool(self):
        common='Warranty applies for 24 months unless excluded by contract.'
        items=[passage(index=index,content=common) for index in range(40)]
        variants=[passage('b',content='Warranty applies for 12 months unless excluded by contract.'),
                  passage('c',content='Warranty does not apply for 24 months unless required by contract.')]
        selected=mmr_pool(items+variants,32)
        self.assertTrue(all(item in selected for item in variants))
        self.assertEqual([item['content'] for item in variants],
                         ['Warranty applies for 12 months unless excluded by contract.',
                          'Warranty does not apply for 24 months unless required by contract.'])

    def test_mmr_ablation_is_the_original_prefix_and_ties_are_stable(self):
        items=[passage(index=index) for index in range(20)]
        self.assertEqual(mmr_pool(items,4,1.0),items[:4])
        self.assertEqual(mmr_pool(items,4),mmr_pool(items,4))
        self.assertEqual(mmr_pool(items,1),items[:1])
        self.assertEqual(mmr_pool(items,0),[])

    def test_diversity_never_scans_past_its_bounded_window(self):
        items=[passage(index=index) for index in range(16)]
        selected=mmr_pool(items+[passage('outside',content='Entirely different evidence')],4)
        self.assertFalse(any(item['document_id']=='outside' for item in selected))

    def test_lambda_configuration_rejects_nonfinite_and_out_of_range_values(self):
        for value in [-0.1,1.1,float('nan'),float('inf')]:
            with self.assertRaises(ValidationError):
                Settings(_env_file=None,rerank_diversity_lambda=value)

    def test_grader_ids_refer_to_the_selected_pool_and_ties_keep_hybrid_order(self):
        settings=Settings(_env_file=None,rerank_candidates=6,rerank_batch_size=6)
        items=[passage(index=index) for index in range(10)]+[passage('b',content='Inspection certificate required.')]
        llm=MagicMock()
        def grade(messages):
            payload=json.loads(messages[-1].content)
            self.assertEqual([item['candidate_id'] for item in payload['candidates']],list(range(6)))
            return RelevanceBatch(items=[RelevanceGrade(candidate_id=item['candidate_id'],grade=3)
                                         for item in payload['candidates']])
        llm.with_structured_output.return_value.invoke.side_effect=grade
        with patch('app.rag.reranking.get_settings',return_value=settings):
            ranked=rerank('Eligibility?',items,llm=llm)
            prefix=rerank('Eligibility?',items,llm=llm,diversify=False)
        self.assertIn('b',[item['document_id'] for item in ranked])
        self.assertNotIn('b',[item['document_id'] for item in prefix])
        self.assertEqual(ranked[0]['chunk_index'],0)
        self.assertEqual(len(ranked),6)

    def test_cross_encoder_gets_the_same_diversified_pool(self):
        settings=Settings(_env_file=None,rerank_backend='cross_encoder',rerank_candidates=6)
        items=[passage(index=index) for index in range(10)]+[passage('b',content='Inspection certificate required.')]
        encoder=MagicMock()
        encoder.predict.side_effect=lambda pairs,**kwargs:[1.0]*len(pairs)
        with patch('app.rag.reranking.get_settings',return_value=settings), \
             patch('app.rag.reranking._cross_encoder',return_value=encoder):
            result=rerank('Eligibility?',items)
        self.assertIn('b',[item['document_id'] for item in result])
        self.assertEqual(len(encoder.predict.call_args.args[0]),6)

    def test_openai_scope_guard_checks_all_candidates_before_mmr(self):
        settings=Settings(_env_file=None,rerank_candidates=6)
        items=[passage(index=index,scope='public') for index in range(30)]+[passage('secret')]
        with patch('app.rag.reranking.get_settings',return_value=settings), \
             patch('app.rag.reranking.mmr_pool') as selection:
            with self.assertRaises(HTTPException):rerank('Q',items,model='openai',llm=MagicMock())
        selection.assert_not_called()

    def test_round_robin_keeps_provenance_and_all_distinct_clauses(self):
        items=[passage(index=0),passage(index=1),passage('b',content='Different clause'),passage(index=2),
               passage(scope='public',content='Public counterpart')]
        result=interleave_sections(items)
        self.assertEqual([(item['scope'],item['document_id'],item['chunk_index']) for item in result],
                         [('private','a',0),('private','b',0),('public','a',0),('private','a',1),('private','a',2)])
        self.assertEqual(len(result),len(items))
        self.assertTrue(all(any(item is source for source in items) for item in result))

    def test_two_appendices_receive_context_space_before_one_uses_the_whole_budget(self):
        settings=Settings(_env_file=None,query_expansion=False,rerank_backend='off',exhaustive_context_chars=2000)
        store=MagicMock(scope='private')
        anchors=[passage(document,content='See Appendix I.',section='Article 1') for document in ('a','b')]
        rows={document:[passage(document,index+1,'x'*450,'Appendix I') for index in range(3)] for document in ('a','b')}
        store.candidates.return_value=anchors
        store.expand.side_effect=lambda source,**kwargs:([source],1)
        store.related_section.side_effect=lambda source,key,limit:(rows[source['document_id']],3)
        with patch('app.rag.evidence.get_settings',return_value=settings), \
             patch('app.rag.reranking.get_settings',return_value=settings):
            diverse=retrieve_evidence('Li\u1ec7t k\u00ea Appendix I',[store],MagicMock(),'qwen2.5:7b')
            baseline=retrieve_evidence('Li\u1ec7t k\u00ea Appendix I',[store],MagicMock(),'qwen2.5:7b',use_diversity=False)
        self.assertTrue(all(diverse.coverage['section_retained'][f'private:{document}:appendix:1']>=1 for document in ('a','b')))
        self.assertEqual(baseline.coverage['section_retained']['private:b:appendix:1'],0)
        self.assertTrue(diverse.coverage['completeness_unverified'])
        self.assertLessEqual(diverse.coverage['context_chars'],2000)
        self.assertLessEqual(len(diverse.sources),4)
        self.assertEqual(len({(item['scope'],item['document_id'],item['chunk_index']) for item in diverse.evidence}),len(diverse.evidence))

    def test_complete_evidence_metric_requires_every_labeled_passage(self):
        labels=[{'document_id':'a','chunk_index':0},{'document_id':'b','chunk_index':0}]
        partial=retrieval_metrics([passage()],labels)
        complete=retrieval_metrics([passage(),passage('b')],labels)
        self.assertEqual(partial['recall'],0.5)
        self.assertFalse(partial['complete_evidence'])
        self.assertTrue(complete['complete_evidence'])
        self.assertIsNone(retrieval_metrics([],[])['complete_evidence'])

    def test_cli_ablation_disables_both_methods_and_reports_full_evidence_rate(self):
        with tempfile.TemporaryDirectory() as directory:
            dataset,output=Path(directory)/'queries.jsonl',Path(directory)/'result.json'
            dataset.write_text(json.dumps({'question':'Q','expected_sources':[{'document_id':'a'},{'document_id':'b'}]}),encoding='utf-8')
            store=MagicMock()
            store.collection.name='test_v5'
            store.search.return_value=[passage()]
            with patch('app.evaluate.get_vector_store',return_value=store), \
                 patch('app.evaluate.SessionLocal'), patch('app.evaluate.CataloguedStore',return_value=store), \
                 patch('sys.argv',['evaluate',str(dataset),'--no-diversity','--hybrid-only','--output',str(output)]), \
                 redirect_stdout(io.StringIO()):
                main()
            report=json.loads(output.read_text(encoding='utf-8'))
        self.assertFalse(report['configuration']['diversity_enabled'])
        self.assertEqual(report['summary']['complete_evidence_rate'],0)
        self.assertEqual(report['summary']['recall_at_k'],0.5)
        self.assertEqual(store.search.call_args.kwargs,{'use_rerank':False,'use_diversity':False})


if __name__=='__main__':unittest.main()
