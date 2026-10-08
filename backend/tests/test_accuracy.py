import tempfile
import io
import json
from contextlib import redirect_stdout
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from zipfile import ZipFile
from langchain_core.documents import Document
from langchain_core.messages import AIMessage
from app.core.config import Settings
from app.evaluate import expected_sources, retrieval_metrics
from app.rag.chunking import load_chunks
from app.rag.citations import citations_valid
from app.rag.reranking import RelevanceBatch, RelevanceGrade, rerank
from app.rag.retrieval import select_sources
from app.services.rag_service import ABSTAIN, _generate


class AccuracyTests(unittest.TestCase):
    def setUp(self):
        self.settings = Settings(_env_file=None, rerank_batch_size=2)
        self.candidates = [
            {'document_id': 'a', 'document': 'A.pdf', 'content': 'Bảo hành 24 tháng', 'chunk_index': 0},
            {'document_id': 'a', 'document': 'A.pdf', 'content': 'Điều kiện bảo hành', 'chunk_index': 1},
            {'document_id': 'b', 'document': 'B.pdf', 'content': 'Quy định nghỉ phép', 'chunk_index': 0},
        ]

    def grader(self, batches):
        llm = MagicMock()
        llm.with_structured_output.return_value.invoke.side_effect = [
            RelevanceBatch(items=[RelevanceGrade(candidate_id=i, grade=grade) for i, grade in items])
            for items in batches]
        return llm

    def test_reranking_uses_ids_not_response_order_and_rejects_irrelevant(self):
        llm = self.grader([[(1, 3), (0, 2)], [(2, 0)]])
        with patch('app.rag.reranking.get_settings', return_value=self.settings), \
             patch('app.rag.reranking.ChatOllama', return_value=llm):
            ranked = rerank('bảo hành?', self.candidates)
        self.assertEqual([item['chunk_index'] for item in ranked], [1, 0])
        self.assertEqual([item['rerank_score'] for item in ranked], [3, 2])
        self.assertEqual(llm.with_structured_output.return_value.invoke.call_count, 2)

    def test_all_irrelevant_produces_no_sources(self):
        llm = self.grader([[(0, 0), (1, 1)], [(2, 0)]])
        with patch('app.rag.reranking.get_settings', return_value=self.settings), \
             patch('app.rag.reranking.ChatOllama', return_value=llm):
            self.assertEqual(rerank('không có trong tài liệu', self.candidates), [])

    def test_invalid_rerank_ids_fall_back_without_losing_candidates(self):
        for grades in [[(0, 2), (0, 3)], [(0, 2)], [(0, 2), (99, 3)]]:
            llm = self.grader([grades])
            with patch('app.rag.reranking.get_settings', return_value=self.settings), \
                 patch('app.rag.reranking.ChatOllama', return_value=llm):
                ranked = rerank('question', self.candidates)
            self.assertEqual([item['content'] for item in ranked], [item['content'] for item in self.candidates])
            self.assertTrue(all(item['rerank_method'] == 'hybrid_fallback' for item in ranked))

    def test_ablation_does_not_invoke_rerank_model(self):
        with patch('app.rag.reranking.ChatOllama') as llm:
            self.assertEqual(rerank('question', self.candidates, enabled=False), self.candidates)
            llm.assert_not_called()

    def test_cross_encoder_scores_and_threshold(self):
        settings = self.settings.model_copy(update={'rerank_backend': 'cross_encoder', 'cross_encoder_min_score': 0.5})
        encoder = MagicMock()
        encoder.predict.return_value = [0.6, 0.8, 0.1]
        with patch('app.rag.reranking.get_settings', return_value=settings), \
             patch('app.rag.reranking._cross_encoder', return_value=encoder):
            ranked = rerank('question', self.candidates)
        self.assertEqual([item['rerank_score'] for item in ranked], [0.8, 0.6])

    def test_per_document_limit_preserves_highest_ranked_two(self):
        candidates = [self.candidates[1], self.candidates[0],
                      {**self.candidates[0], 'content': 'Third passage', 'chunk_index': 9}, self.candidates[2]]
        selected = select_sources(candidates, 6, 10000)
        self.assertEqual([item['chunk_index'] for item in selected], [1, 0, 0])
        self.assertEqual([item['source_id'] for item in selected], ['S1', 'S2', 'S3'])

    def test_docx_heading_and_header_follow_each_table_row(self):
        xml = '''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>
<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Điều 2. Bảo hành</w:t></w:r></w:p>
<w:p><w:r><w:t>Áp dụng cho thiết bị.</w:t></w:r></w:p>
<w:tbl><w:tr><w:trPr><w:tblHeader/></w:trPr><w:tc><w:p><w:r><w:t>Thiết bị</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>Tháng</w:t></w:r></w:p></w:tc></w:tr>
<w:tr><w:tc><w:p><w:r><w:t>AB987</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>24</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Điều 3. Loại trừ</w:t></w:r></w:p>
<w:p><w:r><w:t>Không áp dụng cho hư hỏng do nước.</w:t></w:r></w:p></w:body></w:document>'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'table.docx'
            with ZipFile(path, 'w') as archive:
                archive.writestr('word/document.xml', xml)
            chunks = load_chunks(path)
        row = next(chunk for chunk in chunks if 'AB987' in chunk.page_content)
        self.assertIn('Thiết bị | Tháng\nAB987 | 24', row.page_content)
        self.assertEqual(row.metadata['section'], 'Điều 2. Bảo hành')
        self.assertFalse(any('AB987' in chunk.page_content and 'Loại trừ' in chunk.page_content for chunk in chunks))
        self.assertTrue(all('page' not in chunk.metadata for chunk in chunks))

    def test_pdf_section_scope_crosses_page_but_chunks_do_not(self):
        pages = [Document(page_content='Điều 1. Phạm vi\nNội dung A', metadata={'page': 0}),
                 Document(page_content='Nội dung tiếp theo\nĐiều 2. Điều kiện\nNội dung B', metadata={'page': 1})]
        with patch('app.rag.chunking.PyPDFLoader') as loader:
            loader.return_value.lazy_load.return_value = pages
            chunks = load_chunks(Path('test.pdf'))
        self.assertEqual([(chunk.metadata['page'], chunk.metadata['section']) for chunk in chunks],
                         [(1, 'Điều 1. Phạm vi'), (2, 'Điều 1. Phạm vi'), (2, 'Điều 2. Điều kiện')])

    def test_citation_repair_rejects_unknown_source_ids(self):
        llm = MagicMock()
        llm.invoke.side_effect = [AIMessage(content='24 tháng [S99]'), AIMessage(content='24 tháng [S1]')]
        with patch('app.services.rag_service._llm', return_value=llm):
            text = _generate('prompt', [{'source_id': 'S1'}])
        self.assertEqual(text, '24 tháng [S1]')
        self.assertEqual(llm.invoke.call_count, 2)

    def test_unrepaired_citation_failure_abstains(self):
        llm = MagicMock()
        llm.invoke.return_value = AIMessage(content='Unsupported assertion [S99]')
        with patch('app.services.rag_service._llm', return_value=llm):
            self.assertEqual(_generate('prompt', [{'source_id': 'S1'}]), ABSTAIN)
        self.assertFalse(citations_valid('no citations', [{'source_id': 'S1'}]))
        self.assertFalse(citations_valid('```code [S1]```', [{'source_id': 'S1'}]))
        self.assertFalse(citations_valid('`[S1]`', [{'source_id': 'S1'}]))

    def test_evaluation_cli_saves_positive_and_negative_results(self):
        from app.evaluate import main
        with tempfile.TemporaryDirectory() as directory:
            dataset = Path(directory) / 'queries.jsonl'
            output = Path(directory) / 'result.json'
            dataset.write_text(json.dumps({'question': 'warranty', 'expected_sources': [{'document': 'A.pdf', 'page': 2}]})
                               + '\n' + json.dumps({'question': 'unanswerable', 'expected_sources': []}), encoding='utf-8')
            store = MagicMock()
            store.collection.name = 'test_collection'
            store.search.side_effect = [[{'document': 'A.pdf', 'page': 2}], []]
            with patch('app.evaluate.get_vector_store', return_value=store), \
                 patch('sys.argv', ['evaluate', str(dataset), '--hybrid-only', '--output', str(output)]), \
                 redirect_stdout(io.StringIO()):
                main()
            report = json.loads(output.read_text(encoding='utf-8'))
        self.assertEqual(report['summary']['recall_at_k'], 1)
        self.assertEqual(report['summary']['precision_returned'], 1)
        self.assertEqual(report['summary']['retrieval_abstention_accuracy'], 1)
        self.assertEqual(report['configuration']['collection'], 'test_collection')
        self.assertTrue(report['configuration']['hybrid_only'])
        self.assertEqual(store.search.call_args_list[0].kwargs, {'use_rerank': False})

    def test_evaluation_distinguishes_wrong_page_from_correct_document(self):
        sources = [{'document': 'A.pdf', 'page': 1, 'chunk_index': 0}]
        labels = expected_sources({'question': 'test', 'expected_sources': [{'document': 'A.pdf', 'page': 2}]})
        self.assertEqual(retrieval_metrics(sources, labels)['recall'], 0)
        self.assertEqual(retrieval_metrics(sources, [{'document': 'A.pdf'}])['recall'], 1)
        self.assertTrue(retrieval_metrics([], [])['correct_abstention'])
        self.assertFalse(retrieval_metrics(sources, [])['correct_abstention'])


if __name__ == '__main__':
    unittest.main()
