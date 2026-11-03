"""Hybrid search combining BM25 keyword search with FAISS embedding search.

Supports four modes:
  - keyword     -- BM25 only
  - embedding   -- FAISS vector similarity only
  - hybrid      -- Reciprocal Rank Fusion (RRF) over both result lists
  - hybrid_rerank -- RRF followed by an optional reranking step
"""

import logging
from typing import Dict, List, Tuple

from .bm25 import BM25Index
from .embeddings import EmbeddingsGenerator
from .faiss_index import FaissIndexManager

logger = logging.getLogger(__name__)

# Standard RRF constant (from Cormack et al. 2009)
RRF_K = 60


def reciprocal_rank_fusion(
    ranked_lists: List[List[Tuple[str, float]]],
    k: int = RRF_K,
) -> List[Tuple[str, float]]:
    """Merge multiple ranked result lists using Reciprocal Rank Fusion.

    For each document d appearing in any list:
        score(d) = sum(1 / (k + rank_i(d)))
    where rank_i starts at 1 for the top result in list i.

    Parameters
    ----------
    ranked_lists : list of list of (file_path, original_score)
        Each inner list is already sorted best-first.
    k : int
        RRF smoothing constant (default 60).

    Returns
    -------
    list of (file_path, rrf_score) sorted descending by rrf_score.
    """
    fused_scores: Dict[str, float] = {}

    for result_list in ranked_lists:
        for rank_zero_based, (file_path, _original_score) in enumerate(result_list):
            rank = rank_zero_based + 1  # RRF uses 1-based ranks
            fused_scores[file_path] = fused_scores.get(file_path, 0.0) + 1.0 / (k + rank)

    merged = sorted(fused_scores.items(), key=lambda x: x[1], reverse=True)
    return merged


class HybridSearcher:
    """Orchestrates keyword, embedding, and hybrid search across BM25 and FAISS."""

    def __init__(
        self,
        bm25_index: BM25Index,
        embeddings_generator: EmbeddingsGenerator,
        faiss_index_manager: FaissIndexManager,
    ):
        self.bm25 = bm25_index
        self.embeddings = embeddings_generator
        self.faiss = faiss_index_manager

    def search(
        self, query: str, k: int = 5, mode: str = "hybrid"
    ) -> List[Tuple[str, float]]:
        """Run a search in the given mode.

        Parameters
        ----------
        query : str
            The user's search query.
        k : int
            Number of results to return.
        mode : str
            One of "keyword", "embedding", "hybrid", "hybrid_rerank".

        Returns
        -------
        list of (file_path, score) tuples, best first.
        """
        if mode == "keyword":
            return self._keyword_search(query, k)
        elif mode == "embedding":
            return self._embedding_search(query, k)
        elif mode == "hybrid":
            return self._hybrid_search(query, k)
        elif mode == "hybrid_rerank":
            return self._hybrid_rerank_search(query, k)
        else:
            raise ValueError(f"Unknown search mode: {mode}")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _keyword_search(self, query: str, k: int) -> List[Tuple[str, float]]:
        return self.bm25.search(query, k)

    def _embedding_search(self, query: str, k: int) -> List[Tuple[str, float]]:
        query_vec = self.embeddings.generate_embedding(query)
        if query_vec is None:
            return []
        raw = self.faiss.search(query_vec, k)
        # Convert FAISS L2 distances to similarity scores
        return [(path, 1.0 / (1.0 + dist)) for path, dist in raw]

    def _hybrid_search(self, query: str, k: int) -> List[Tuple[str, float]]:
        """Combine BM25 and embedding results via Reciprocal Rank Fusion."""
        # Fetch more candidates from each source so RRF has room to merge
        fetch_k = k * 3
        bm25_results = self._keyword_search(query, fetch_k)
        emb_results = self._embedding_search(query, fetch_k)

        fused = reciprocal_rank_fusion([bm25_results, emb_results])
        return fused[:k]

    def _hybrid_rerank_search(self, query: str, k: int) -> List[Tuple[str, float]]:
        """RRF fusion then optional reranking.

        Reranking with a cross-encoder or external model is attempted but
        gracefully skipped if the necessary library is unavailable.
        """
        # Start with standard hybrid results (get extra candidates for reranking)
        candidates = self._hybrid_search(query, k * 2)

        try:
            reranked = self._rerank(query, candidates, k)
            return reranked
        except Exception as exc:
            logger.debug("Reranking unavailable, falling back to RRF: %s", exc)
            return candidates[:k]

    def _rerank(
        self, query: str, candidates: List[Tuple[str, float]], k: int
    ) -> List[Tuple[str, float]]:
        """Attempt cross-encoder reranking. Raises if dependencies are missing."""
        # Try to use sentence-transformers CrossEncoder
        from sentence_transformers import CrossEncoder  # type: ignore

        model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
        pairs = [(query, path) for path, _score in candidates]
        ce_scores = model.predict(pairs)

        reranked = [
            (candidates[i][0], float(ce_scores[i]))
            for i in range(len(candidates))
        ]
        reranked.sort(key=lambda x: x[1], reverse=True)
        return reranked[:k]
