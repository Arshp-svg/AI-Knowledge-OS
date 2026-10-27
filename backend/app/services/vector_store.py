import uuid
import logging
from pathlib import Path
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
from app.core.config import settings

logger = logging.getLogger(__name__)

class VectorStore:
    def __init__(self, collection_name: str = "documents", dim: int = 384):
        self.collection_name = collection_name
        self.dim = dim
        
        if settings.qdrant_url:
            logger.info(f"Connecting to remote Qdrant vector database at {settings.qdrant_url}")
            self.client = QdrantClient(
                url=settings.qdrant_url,
                api_key=settings.qdrant_api_key or None,
                timeout=10.0
            )
        else:
            # Persist vectors on local disk inside backend/storage/qdrant_db
            db_path = Path("storage/qdrant_db")
            db_path.mkdir(parents=True, exist_ok=True)
            self.client = QdrantClient(path=str(db_path))

        # Create collection if it doesn't already exist
        try:
            if not self.client.collection_exists(collection_name=self.collection_name):
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(size=self.dim, distance=Distance.COSINE),
                )
        except Exception as exc:
            logger.warning(f"Could not verify or create collection '{self.collection_name}': {exc}")

    def check_health(self) -> dict:
        try:
            exists = self.client.collection_exists(self.collection_name)
            points_count = 0
            if exists:
                col_info = self.client.get_collection(self.collection_name)
                points_count = col_info.points_count or 0
            return {
                "status": "healthy",
                "mode": "remote" if settings.qdrant_url else "embedded",
                "collection": self.collection_name,
                "collection_exists": exists,
                "points_count": points_count
            }
        except Exception as exc:
            return {
                "status": "unhealthy",
                "mode": "remote" if settings.qdrant_url else "embedded",
                "error": str(exc)
            }

    def add(self, embeddings, texts: list[str], metadatas: list[dict]):
        points = []
        for i, (emb, text, meta) in enumerate(zip(embeddings, texts, metadatas)):
            # Qdrant accepts either integer IDs or UUID strings
            point_id = str(uuid.uuid4())
            
            # Combine chunk text and metadata into a single payload dictionary
            payload = {
                "text": text,
                **meta
            }
            
            points.append(
                PointStruct(
                    id=point_id,
                    vector=emb.tolist() if hasattr(emb, "tolist") else emb,
                    payload=payload
                )
            )

        # Batch points upsert in blocks of 32 to prevent memory bloat and network payload spikes
        batch_size = 32
        for idx in range(0, len(points), batch_size):
            self.client.upsert(
                collection_name=self.collection_name,
                points=points[idx:idx + batch_size]
            )
        del points

    def search(self, query_embedding, top_k: int = 4):
        # Handle numpy arrays and nested lists safely
        if hasattr(query_embedding, "tolist"):
            query_embedding = query_embedding.tolist()
        if isinstance(query_embedding, list) and len(query_embedding) > 0 and isinstance(query_embedding[0], list):
            vector = query_embedding[0]
        else:
            vector = query_embedding

        # Qdrant Query API
        response = self.client.query_points(
            collection_name=self.collection_name,
            query=vector,
            limit=top_k
        )

        results = []
        for hit in response.points:
            payload = hit.payload or {}
            results.append({
                "text": payload.get("text", ""),
                "metadata": {k: v for k, v in payload.items() if k != "text"},
                "score": hit.score
            })

        return results

    def delete_by_document_id(self, doc_id: str):
        try:
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="document_id",
                            match=MatchValue(value=doc_id)
                        )
                    ]
                )
            )
        except Exception:
            pass
