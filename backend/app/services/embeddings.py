import os
import gc
import numpy as np
import torch

# Enforce single-threaded CPU execution to prevent OpenMP memory spikes on 512MB cloud instances
torch.set_num_threads(1)
if hasattr(torch, "set_num_interop_threads"):
    try:
        torch.set_num_interop_threads(1)
    except RuntimeError:
        pass

from sentence_transformers import SentenceTransformer

class EmbeddingService:
    def __init__(self):
        self.model = SentenceTransformer(
            "sentence-transformers/all-MiniLM-L6-v2",
            device="cpu"
        )
        self.model.eval()

    def embed_texts(self, texts: list[str], batch_size: int = 16) -> np.ndarray:
        if not texts:
            return np.empty((0, 384), dtype=np.float32)

        # Process in conservative micro-batches with explicit garbage collection
        # to ensure peak RAM stays strictly under 512MB on cloud free tiers
        all_embeddings = []
        with torch.inference_mode():
            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + batch_size]
                emb = self.model.encode(
                    batch,
                    batch_size=batch_size,
                    show_progress_bar=False,
                    convert_to_numpy=True,
                    normalize_embeddings=True
                )
                all_embeddings.append(emb)
                gc.collect()

        result = np.vstack(all_embeddings).astype("float32")
        del all_embeddings
        gc.collect()
        return result

