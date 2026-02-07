from app.services.embeddings import EmbeddingService
from app.services.vector_store import VectorStore

embedding_service = EmbeddingService()
vector_store = VectorStore(dim=384)
