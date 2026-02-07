from fastapi import APIRouter
from pydantic import BaseModel
from app.core.state import embedding_service, vector_store

router = APIRouter(prefix="/search", tags=["search"])

class SearchRequest(BaseModel):
    query: str
    top_k: int = 5

@router.post("/")
def semantic_search(request: SearchRequest):
    query_embedding = embedding_service.embed_texts([request.query])
    results = vector_store.search(query_embedding, top_k=request.top_k)
    return {"results": results}
