from typing import List, Dict, Any
from pathlib import Path
from flashrank import Ranker, RerankRequest

import os

class RerankerService:
    """
    Cross-Encoder neural reranker powered by FlashRank (lightweight, runs fast on CPU).
    Re-scores and re-ranks candidate passages retrieved from dense & sparse stages.
    """
    def __init__(self, model_name: str = "ms-marco-TinyBERT-L-2-v2"):
        self.model_name = model_name
        self._ranker = None

    @property
    def ranker(self) -> Ranker:
        if self._ranker is None:
            cache_env = os.environ.get("FLASHRANK_CACHE_DIR", "/home/appuser/.cache/flashrank")
            cache_dir = Path(cache_env)
            if not cache_dir.exists():
                cache_dir = Path("storage/flashrank_cache")
            cache_dir.mkdir(parents=True, exist_ok=True)
            self._ranker = Ranker(model_name=self.model_name, cache_dir=str(cache_dir))
        return self._ranker

    def rerank(self, query: str, passages: List[Dict[str, Any]], top_k: int = 4) -> List[Dict[str, Any]]:
        if not passages:
            return []

        # FlashRank expects a list of dicts with 'id' and 'text'
        flashrank_passages = [
            {
                "id": str(i),
                "text": p.get("text", ""),
                "meta": p.get("metadata", {})
            }
            for i, p in enumerate(passages)
        ]

        rerank_request = RerankRequest(query=query, passages=flashrank_passages)
        results = self.ranker.rerank(rerank_request)

        reranked_chunks = []
        for hit in results[:top_k]:
            reranked_chunks.append({
                "text": hit["text"],
                "metadata": hit.get("meta", {}),
                "score": round(float(hit.get("score", 0.0)), 4)
            })

        return reranked_chunks
