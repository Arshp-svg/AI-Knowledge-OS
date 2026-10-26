from app.services.embeddings import EmbeddingService
from app.services.vector_store import VectorStore
from app.services.reranker import RerankerService
from app.services.hybrid_retriever import HybridRetriever

embedding_service = EmbeddingService()
vector_store = VectorStore(dim=384)
reranker_service = RerankerService()

hybrid_retriever = HybridRetriever(
    vector_store=vector_store,
    embedding_service=embedding_service,
    reranker=reranker_service
)
