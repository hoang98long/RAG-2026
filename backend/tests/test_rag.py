import tempfile
import unittest
import unicodedata
from pathlib import Path
from unittest.mock import patch
from langchain_core.documents import Document
from pydantic import ValidationError
from app.core.config import Settings
from app.rag.chunking import load_chunks, normalize_text
from app.rag.retrieval import BM25Index, fuse_rankings, select_sources
from app.rag.vector_store import VectorStore
from app.services.rag_service import _context, _llm


class FakeEmbeddings:
    queries = []

    def __init__(self, **kwargs):
        pass

    def embed_documents(self, texts):
        return [[1.0, 0.0] if "bảo hành" in text else [0.0, 1.0] for text in texts]

    def embed_query(self, query):
        self.queries.append(query)
        return [1.0, 0.0]


class RetrievalTests(unittest.TestCase):
    def test_unicode_normalization_preserves_paragraphs(self):
        text = unicodedata.normalize("NFD", "Bảo hành") + "  24 tháng\r\n\r\nĐiều kiện\x00"
        self.assertEqual(normalize_text(text), "Bảo hành 24 tháng\n\nĐiều kiện")

    def test_bm25_finds_code_and_empty_query(self):
        index = BM25Index(["Quy định chung", "Mã AB-987 bảo hành 24 tháng", "Mã XY-123"])
        self.assertEqual(index.search("AB-987", 2)[0], 1)
        self.assertEqual(index.search("", 4), [])
        self.assertEqual(BM25Index([]).search("bảo hành", 4), [])

    def test_fusion_rewards_agreement(self):
        self.assertEqual(fuse_rankings(["a", "b"], ["b", "c"])[0][0], "b")

    def test_duplicates_budget_and_distinct_numbers(self):
        candidates = [{"document": "A", "content": text} for text in
                      ["Bảo hành 24 tháng", "Bảo hành 24 tháng", "Bảo hành 12 tháng"]]
        sources = select_sources(candidates, 6, 1000)
        self.assertEqual([s["source_id"] for s in sources], ["S1", "S2"])
        self.assertEqual(select_sources(candidates, 6, 20), [])

    def test_settings_validation(self):
        for overrides in ({"chunk_overlap": 1600}, {"retrieval_candidates": 2},
                          {"llm_num_predict": 16384}):
            with self.assertRaises(ValidationError):
                Settings(_env_file=None, **overrides)

    def test_page_boundaries_and_chunk_metadata(self):
        settings = Settings(_env_file=None, chunk_size=200, chunk_overlap=30)
        pages = [Document(page_content="Bảo hành 24 tháng. " * 30, metadata={"page": 0}),
                 Document(page_content="Điều kiện áp dụng. " * 30, metadata={"page": 1})]
        with patch("app.rag.chunking.get_settings", return_value=settings), \
             patch("app.rag.chunking.PyPDFLoader") as loader:
            loader.return_value.lazy_load.return_value = pages
            chunks = load_chunks(Path("example.pdf"))
        self.assertEqual({c.metadata["page"] for c in chunks}, {1, 2})
        self.assertTrue(all(len(c.page_content) <= 200 for c in chunks))
        self.assertTrue(all(not ("Bảo hành" in c.page_content and "Điều kiện" in c.page_content) for c in chunks))
        self.assertEqual([c.metadata["chunk_index"] for c in chunks], list(range(len(chunks))))

    def test_llm_options_and_source_labels(self):
        settings = Settings(_env_file=None)
        with patch("app.services.rag_service.get_settings", return_value=settings):
            llm = _llm()
        self.assertEqual(llm.model, "qwen2.5:7b")
        self.assertEqual(llm.num_ctx, 16384)
        self.assertEqual(llm.temperature, 0)
        text = _context([{"source_id": "S1", "document": "A.pdf", "page": 2,
                          "chunk_index": 0, "content": "Nội dung"}])
        self.assertIn("[S1] A.pdf, trang 2, đoạn 1", text)

    def test_real_chroma_hybrid_reindex_and_delete(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(_env_file=None, chroma_dir=directory, embedding_batch_size=1, rerank_backend="off")
            with patch("app.rag.vector_store.get_settings", return_value=settings), \
                 patch("app.rag.vector_store.OllamaEmbeddings", FakeEmbeddings), \
                 patch("app.rag.reranking.get_settings", return_value=settings):
                store = VectorStore()
                self.assertEqual(store.search("test", 6), [])
                store.add("doc-a", "A.pdf", [Document(page_content="bảo hành 24 tháng", metadata={"page": 2}),
                                             Document(page_content="Mã thiết bị AB987")])
                store.add("doc-b", "B.docx", [Document(page_content="Mã thiết bị XY123")])
                self.assertEqual([chunk["chunk_index"] for chunk in store.document_chunks("doc-a")], [0, 1])
                self.assertEqual(store.document_chunks("missing"), [])
                sources = store.search("AB987", 6)
                self.assertEqual(sources[0]["content"], "Mã thiết bị AB987")
                self.assertTrue(FakeEmbeddings.queries[-1].startswith("Instruct:"))
                self.assertEqual(store.search("thời hạn bảo hành", 6)[0]["page"], 2)
                # Reindex to fewer chunks, and verify lexical cache invalidation.
                store.add("doc-a", "A.pdf", [Document(page_content="bảo hành 12 tháng", metadata={"page": 3})])
                self.assertEqual(store.collection.count(), 2)
                self.assertFalse(any("24" in s["content"] for s in store.search("bảo hành", 6)))
                store.client.get_or_create_collection("documents").add(
                    ids=["legacy"], embeddings=[[1.0, 0.0]], documents=["old"],
                    metadatas=[{"document_id": "doc-a"}])
                # Changing chunk config produces a separate compatible collection.
                with patch("app.rag.vector_store.get_settings", return_value=settings.model_copy(update={"chunk_size": 1800})):
                    other = VectorStore()
                self.assertNotEqual(store.collection.name, other.collection.name)
                other.add("doc-a", "A.pdf", [Document(page_content="bảo hành 12 tháng")])
                store.delete_document("doc-a")
                self.assertEqual(store.collection.count(), 1)
                self.assertEqual(other.collection.count(), 0)
                self.assertEqual(store.client.get_collection("documents").count(), 0)
                # Release Chroma file handles before TemporaryDirectory cleanup on Windows.
                store.client._system.stop()


if __name__ == "__main__":
    unittest.main()
