"""Lightweight BM25 keyword search over file contents."""

import math
from collections import Counter
from typing import Dict, List, Tuple


def _tokenize(text: str) -> List[str]:
    """Simple whitespace + lowercasing tokenizer."""
    # Strip punctuation and split on whitespace
    cleaned = ""
    for ch in text.lower():
        if ch.isalnum() or ch == " ":
            cleaned += ch
        else:
            cleaned += " "
    return [tok for tok in cleaned.split() if len(tok) > 1]


class BM25Index:
    """BM25 (Okapi) scoring over a set of documents.

    Parameters
    ----------
    k1 : float
        Term-frequency saturation parameter (default 1.5).
    b : float
        Length-normalization parameter (default 0.75).
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b

        # Indexed data
        self.file_paths: List[str] = []
        self.doc_term_freqs: List[Dict[str, int]] = []
        self.doc_lengths: List[int] = []
        self.avg_dl: float = 0.0
        self.n_docs: int = 0

        # Inverted index: term -> set of doc indices that contain it
        self.doc_freq: Dict[str, int] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_documents(self, file_paths: List[str], contents: List[str]) -> None:
        """Index a batch of documents.

        Parameters
        ----------
        file_paths : list[str]
            One path per document.
        contents : list[str]
            Corresponding text content for each document.
        """
        if len(file_paths) != len(contents):
            raise ValueError("file_paths and contents must have the same length")

        for path, text in zip(file_paths, contents):
            tokens = _tokenize(text)
            tf = Counter(tokens)

            idx = self.n_docs
            self.file_paths.append(path)
            self.doc_term_freqs.append(dict(tf))
            self.doc_lengths.append(len(tokens))
            self.n_docs += 1

            for term in tf:
                self.doc_freq[term] = self.doc_freq.get(term, 0) + 1

        # Recompute average document length
        total = sum(self.doc_lengths) if self.doc_lengths else 0
        self.avg_dl = total / self.n_docs if self.n_docs else 0.0

    def search(self, query: str, k: int = 5) -> List[Tuple[str, float]]:
        """Return the top-k documents ranked by BM25 score.

        Returns a list of ``(file_path, score)`` tuples sorted descending by
        score.
        """
        if self.n_docs == 0:
            return []

        query_tokens = _tokenize(query)
        if not query_tokens:
            return []

        scores: List[float] = [0.0] * self.n_docs

        for term in query_tokens:
            if term not in self.doc_freq:
                continue

            df = self.doc_freq[term]
            # IDF with smoothing to avoid negatives for very common terms
            idf = math.log((self.n_docs - df + 0.5) / (df + 0.5) + 1.0)

            for doc_idx in range(self.n_docs):
                tf = self.doc_term_freqs[doc_idx].get(term, 0)
                if tf == 0:
                    continue
                dl = self.doc_lengths[doc_idx]
                numerator = tf * (self.k1 + 1)
                denominator = tf + self.k1 * (1 - self.b + self.b * dl / self.avg_dl)
                scores[doc_idx] += idf * (numerator / denominator)

        # Build ranked list
        ranked = [
            (self.file_paths[i], scores[i])
            for i in range(self.n_docs)
            if scores[i] > 0
        ]
        ranked.sort(key=lambda x: x[1], reverse=True)
        return ranked[:k]
