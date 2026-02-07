from fastapi import APIRouter
from pydantic import BaseModel
from app.core.state import embedding_service, vector_store
from app.services.llm import generate_answer

router = APIRouter(prefix="/ask", tags=["ask"])

class AskRequest(BaseModel):
    question: str
    top_k: int = 4

@router.post("/")
def ask_question(request: AskRequest):
    query_embedding = embedding_service.embed_texts([request.question])
    retrieved_chunks = vector_store.search(
        query_embedding,
        top_k=request.top_k
    )

    context = "\n\n".join(
        f"[Source {i+1}] {chunk['text']}"
        for i, chunk in enumerate(retrieved_chunks)
    )

    answer = generate_answer(
        context=context,
        question=request.question
    )

    return {
        "question": request.question,
        "answer": answer,
        "sources": retrieved_chunks
    }
