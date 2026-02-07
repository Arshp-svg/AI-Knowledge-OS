import faiss
import numpy as np

class VectorStore:
    def __init__(self, dim: int):
        self.index = faiss.IndexFlatL2(dim)
        self.texts = []
        self.metadatas = []

    def add(self, embeddings: np.ndarray, texts: list[str], metadatas: list[dict]):
        self.index.add(embeddings)
        self.texts.extend(texts)
        self.metadatas.extend(metadatas)

    def search(self, query_embedding: np.ndarray, top_k: int = 5):
        distances, indices = self.index.search(query_embedding, top_k)
        results = []

        for idx in indices[0]:
            if idx == -1:
                continue
            results.append({
                "text": self.texts[idx],
                "metadata": self.metadatas[idx]
            })

        return results
