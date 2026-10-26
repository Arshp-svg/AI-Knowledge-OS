from fastapi import APIRouter, Request
from pydantic import BaseModel
from app.core.state import hybrid_retriever
from app.core.security import limiter

router = APIRouter(prefix="/search", tags=["search"])

class SearchRequest(BaseModel):
    query: str
    top_k: int = 5

@router.post("/")
@limiter.limit("30/minute")
def hybrid_search(request: Request, body: SearchRequest):
    results = hybrid_retriever.search(
        query=body.query,
        top_k=body.top_k
    )
    return {"results": results}
