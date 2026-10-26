import re
from typing import List, Dict, Any
from rank_bm25 import BM25Okapi

from app.services.vector_store import VectorStore
from app.services.embeddings import EmbeddingService
from app.services.reranker import RerankerService

class HybridRetriever:
    """
    Two-stage Hybrid Retrieval Engine:
    1. Candidate Retrieval: Dense Vector Search (Qdrant) + Sparse Keyword Search (BM25)
    2. Fusion: Reciprocal Rank Fusion (RRF)
    3. Re-ranking: Neural Cross-Encoder (FlashRank)
    """
    def __init__(
        self,
        vector_store: VectorStore,
        embedding_service: EmbeddingService,
        reranker: RerankerService
    ):
        self.vector_store = vector_store
        self.embedding_service = embedding_service
        self.reranker = reranker

    def _tokenize(self, text: str) -> List[str]:
        return re.findall(r"\w+", text.lower())

    def _get_all_stored_chunks(self) -> List[Dict[str, Any]]:
        """
        Scrolls all indexed chunks from Qdrant with payloads for BM25 indexing.
        """
        try:
            points, _ = self.vector_store.client.scroll(
                collection_name=self.vector_store.collection_name,
                limit=10000,
                with_payload=True,
                with_vectors=False
            )
            chunks = []
            for pt in points:
                payload = pt.payload or {}
                chunks.append({
                    "id": str(pt.id),
                    "text": payload.get("text", ""),
                    "metadata": {k: v for k, v in payload.items() if k != "text"}
                })
            return chunks
        except Exception:
            return []

    def _bm25_search(self, query: str, chunks: List[Dict[str, Any]], top_k: int = 15) -> List[Dict[str, Any]]:
        if not chunks:
            return []

        tokenized_corpus = [self._tokenize(c["text"]) for c in chunks]
        tokenized_query = self._tokenize(query)

        if not tokenized_query:
            return chunks[:top_k]

        bm25 = BM25Okapi(tokenized_corpus)
        scores = bm25.get_scores(tokenized_query)

        scored_chunks = []
        for idx, score in enumerate(scores):
            if score > 0:
                chunk_copy = dict(chunks[idx])
                chunk_copy["bm25_score"] = float(score)
                scored_chunks.append(chunk_copy)

        scored_chunks.sort(key=lambda x: x.get("bm25_score", 0), reverse=True)
        return scored_chunks[:top_k]

    def _reciprocal_rank_fusion(
        self,
        dense_results: List[Dict[str, Any]],
        sparse_results: List[Dict[str, Any]],
        rrf_k: int = 60
    ) -> List[Dict[str, Any]]:
        """
        Merges rankings from Dense and BM25 searches using standard RRF formula:
        RRF_Score(doc) = sum(1 / (k + rank))
        """
        rrf_scores: Dict[str, float] = {}
        doc_map: Dict[str, Dict[str, Any]] = {}

        # Process dense rankings
        for rank, doc in enumerate(dense_results):
            # Key by text signature
            key = doc.get("text", "")[:120]
            doc_map[key] = doc
            rrf_scores[key] = rrf_scores.get(key, 0.0) + (1.0 / (rrf_k + rank + 1))

        # Process sparse (BM25) rankings
        for rank, doc in enumerate(sparse_results):
            key = doc.get("text", "")[:120]
            if key not in doc_map:
                doc_map[key] = doc
            rrf_scores[key] = rrf_scores.get(key, 0.0) + (1.0 / (rrf_k + rank + 1))

        # Sort combined results by RRF score
        sorted_keys = sorted(rrf_scores.keys(), key=lambda k: rrf_scores[k], reverse=True)
        return [doc_map[k] for k in sorted_keys]

    def search(self, query: str, top_k: int = 4, candidate_k: int = 15) -> List[Dict[str, Any]]:
        # 1. Dense Vector Search
        query_emb = self.embedding_service.embed_texts([query])
        dense_candidates = self.vector_store.search(query_emb, top_k=candidate_k)

        # 2. Sparse BM25 Search
        all_chunks = self._get_all_stored_chunks()
        sparse_candidates = self._bm25_search(query, all_chunks, top_k=candidate_k)

        # If both are empty, return nothing
        if not dense_candidates and not sparse_candidates:
            return []

        # 3. Reciprocal Rank Fusion
        fused_candidates = self._reciprocal_rank_fusion(dense_candidates, sparse_candidates)

        # 4. Neural Cross-Encoder Reranking
        reranked_results = self.reranker.rerank(
            query=query,
            passages=fused_candidates,
            top_k=top_k
        )

        return reranked_results
