"""Tests for BM25, embedding, and hybrid search modes."""

import math
import sys
import os
from unittest.mock import MagicMock, patch
from types import ModuleType

import numpy as np
import pytest

# Ensure the backend package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

# Stub out heavy optional dependencies so we can import the search package
# without requiring sentence_transformers or faiss to be installed.
for _mod_name in ("sentence_transformers", "faiss", "faiss.swigfaiss"):
    if _mod_name not in sys.modules:
        sys.modules[_mod_name] = ModuleType(_mod_name)
# Provide the class names our code expects
if not hasattr(sys.modules["sentence_transformers"], "SentenceTransformer"):
    sys.modules["sentence_transformers"].SentenceTransformer = MagicMock
if not hasattr(sys.modules["sentence_transformers"], "CrossEncoder"):
    sys.modules["sentence_transformers"].CrossEncoder = MagicMock

from search.bm25 import BM25Index, _tokenize
from search.hybrid import HybridSearcher, reciprocal_rank_fusion, RRF_K


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

DOCS = {
    "/tmp/a.txt": "the quick brown fox jumps over the lazy dog",
    "/tmp/b.txt": "python is a great programming language for data science",
    "/tmp/c.txt": "the fox and the hound is a classic animated movie",
    "/tmp/d.txt": "machine learning and deep learning are subsets of artificial intelligence",
}


@pytest.fixture
def bm25():
    idx = BM25Index()
    paths = list(DOCS.keys())
    contents = list(DOCS.values())
    idx.add_documents(paths, contents)
    return idx


def _make_fake_embedding(dim=384):
    """Return a deterministic but unique-ish embedding."""
    rng = np.random.RandomState(42)
    return rng.randn(dim).astype(np.float32)


# ---------------------------------------------------------------------------
# BM25 tests
# ---------------------------------------------------------------------------

class TestBM25Basic:
    def test_index_and_search(self, bm25):
        results = bm25.search("fox", k=2)
        assert len(results) > 0
        # Both fox-containing docs should appear
        paths = [r[0] for r in results]
        assert "/tmp/a.txt" in paths
        assert "/tmp/c.txt" in paths

    def test_no_results_for_missing_term(self, bm25):
        results = bm25.search("xyznonexistent", k=5)
        assert results == []

    def test_empty_index(self):
        idx = BM25Index()
        assert idx.search("anything") == []

    def test_scores_are_positive(self, bm25):
        results = bm25.search("programming language", k=4)
        for _path, score in results:
            assert score > 0

    def test_add_documents_length_mismatch(self):
        idx = BM25Index()
        with pytest.raises(ValueError):
            idx.add_documents(["/a"], ["text a", "text b"])


# ---------------------------------------------------------------------------
# Embedding search tests (mocked model)
# ---------------------------------------------------------------------------

class TestEmbeddingSearch:
    def test_embedding_search_returns_results(self):
        """Embedding search should work end-to-end with a mocked model."""
        mock_embeddings = MagicMock()
        mock_embeddings.generate_embedding.return_value = np.ones(384, dtype=np.float32)

        mock_faiss = MagicMock()
        mock_faiss.search.return_value = [
            ("/tmp/a.txt", 0.1),
            ("/tmp/b.txt", 0.5),
        ]

        bm25 = BM25Index()
        searcher = HybridSearcher(bm25, mock_embeddings, mock_faiss)
        results = searcher.search("test query", k=2, mode="embedding")

        assert len(results) == 2
        # Scores should be similarity (converted from distance)
        assert results[0][0] == "/tmp/a.txt"
        assert results[0][1] == pytest.approx(1.0 / 1.1, rel=1e-3)

    def test_embedding_search_empty_when_no_embedding(self):
        mock_embeddings = MagicMock()
        mock_embeddings.generate_embedding.return_value = None

        mock_faiss = MagicMock()
        bm25 = BM25Index()
        searcher = HybridSearcher(bm25, mock_embeddings, mock_faiss)
        results = searcher.search("test", k=5, mode="embedding")
        assert results == []


# ---------------------------------------------------------------------------
# RRF math tests
# ---------------------------------------------------------------------------

class TestRRFMath:
    def test_rrf_single_list(self):
        """RRF with one list should preserve ordering."""
        ranked = [("/a", 10.0), ("/b", 5.0), ("/c", 1.0)]
        fused = reciprocal_rank_fusion([ranked])
        paths = [p for p, _ in fused]
        assert paths == ["/a", "/b", "/c"]

    def test_rrf_formula_exact(self):
        """Verify RRF scores match hand-calculated values."""
        list1 = [("/a", 0), ("/b", 0)]  # a is rank 1, b is rank 2
        list2 = [("/b", 0), ("/a", 0)]  # b is rank 1, a is rank 2

        fused = reciprocal_rank_fusion([list1, list2], k=60)
        scores = {path: score for path, score in fused}

        # /a: 1/(60+1) + 1/(60+2) = 1/61 + 1/62
        expected_a = 1.0 / 61 + 1.0 / 62
        # /b: 1/(60+2) + 1/(60+1) = 1/62 + 1/61
        expected_b = 1.0 / 62 + 1.0 / 61

        assert scores["/a"] == pytest.approx(expected_a)
        assert scores["/b"] == pytest.approx(expected_b)
        # They should be equal since both appear at rank 1 and rank 2
        assert scores["/a"] == pytest.approx(scores["/b"])

    def test_rrf_favors_consistently_ranked_doc(self):
        """A doc ranked #1 in both lists should beat one ranked #1 and #10."""
        list1 = [("/winner", 0)] + [(f"/filler{i}", 0) for i in range(9)]
        list2 = [("/winner", 0)] + [(f"/filler{i}", 0) for i in range(9)]

        list3 = [("/loser", 0)] + [(f"/other{i}", 0) for i in range(9)]
        list4 = [(f"/other{i}", 0) for i in range(9)] + [("/loser", 0)]

        fused_winner = reciprocal_rank_fusion([list1, list2], k=60)
        fused_loser = reciprocal_rank_fusion([list3, list4], k=60)

        winner_score = dict(fused_winner)["/winner"]
        loser_score = dict(fused_loser)["/loser"]

        assert winner_score > loser_score

    def test_rrf_empty_lists(self):
        assert reciprocal_rank_fusion([]) == []
        assert reciprocal_rank_fusion([[], []]) == []


# ---------------------------------------------------------------------------
# Hybrid mode integration tests (mocked backends)
# ---------------------------------------------------------------------------

class TestHybridModes:
    def _make_searcher(self):
        bm25 = BM25Index()
        bm25.add_documents(
            list(DOCS.keys()),
            list(DOCS.values()),
        )

        mock_embeddings = MagicMock()
        mock_embeddings.generate_embedding.return_value = np.ones(384, dtype=np.float32)

        mock_faiss = MagicMock()
        mock_faiss.search.return_value = [
            ("/tmp/b.txt", 0.2),
            ("/tmp/d.txt", 0.4),
            ("/tmp/a.txt", 0.8),
        ]

        return HybridSearcher(bm25, mock_embeddings, mock_faiss)

    def test_keyword_mode(self):
        searcher = self._make_searcher()
        results = searcher.search("fox", k=3, mode="keyword")
        assert len(results) > 0
        paths = [r[0] for r in results]
        assert "/tmp/a.txt" in paths

    def test_embedding_mode(self):
        searcher = self._make_searcher()
        results = searcher.search("anything", k=3, mode="embedding")
        assert len(results) > 0
        # Should reflect mock FAISS ordering
        assert results[0][0] == "/tmp/b.txt"

    def test_hybrid_mode(self):
        searcher = self._make_searcher()
        results = searcher.search("fox", k=3, mode="hybrid")
        assert len(results) > 0
        # All results should have positive scores
        for _path, score in results:
            assert score > 0

    def test_hybrid_rerank_falls_back(self):
        """hybrid_rerank should fall back gracefully when CrossEncoder is missing."""
        searcher = self._make_searcher()
        # Even if cross-encoder import fails, we still get results
        results = searcher.search("fox", k=3, mode="hybrid_rerank")
        assert len(results) > 0

    def test_invalid_mode_raises(self):
        searcher = self._make_searcher()
        with pytest.raises(ValueError, match="Unknown search mode"):
            searcher.search("test", k=3, mode="bogus")

    def test_each_mode_returns_results(self):
        """Every valid mode should return at least one result for a query
        that matches something in the corpus."""
        searcher = self._make_searcher()
        for mode in ("keyword", "embedding", "hybrid"):
            results = searcher.search("programming language", k=3, mode=mode)
            assert len(results) > 0, f"mode={mode} returned no results"
