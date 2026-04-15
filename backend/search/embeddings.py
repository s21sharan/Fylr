import numpy as np
from typing import List
from sentence_transformers import SentenceTransformer


class EmbeddingsGenerator:
    def __init__(self):
        self.model = SentenceTransformer('all-MiniLM-L6-v2')

    def generate_embedding(self, text: str) -> np.ndarray:
        """Generate embedding for a given text using sentence-transformers"""
        return self.model.encode([text])[0]

    def generate_embeddings_batch(self, texts: List[str]) -> List[np.ndarray]:
        """Generate embeddings for a batch of texts"""
        return list(self.model.encode(texts))
