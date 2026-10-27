import os
import gc
from typing import List
import numpy as np
from fastembed import TextEmbedding

class EmbeddingService:
    """
    Lightweight, high-performance ONNX embedding service powered by FastEmbed (by Qdrant).
    Uses sentence-transformers/all-MiniLM-L6-v2 ONNX runtime:
    - Runs in <60MB RAM (vs 350MB+ for PyTorch)
    - Zero PyTorch or CUDA dependencies
    - Produces exact same 384-dimensional cosine vector space
    """
    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        cache_dir = os.environ.get("FASTEMBED_CACHE_PATH", "/home/appuser/.cache/fastembed")
        self.model = TextEmbedding(
            model_name=model_name,
            cache_dir=cache_dir
        )

    def embed_texts(self, texts: List[str], batch_size: int = 32) -> np.ndarray:
        if not texts:
            return np.empty((0, 384), dtype=np.float32)

        # FastEmbed.embed generates an iterator of numpy float32 vectors
        embeddings = list(self.model.embed(texts, batch_size=batch_size))
        result = np.array(embeddings, dtype=np.float32)
        del embeddings
        gc.collect()
        return result


