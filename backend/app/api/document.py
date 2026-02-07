import uuid
from fastapi import APIRouter, UploadFile, File, HTTPException
from pathlib import Path
from datetime import datetime
from app.utils.chunker import chunk_text
from app.models.chunk import Chunk
from app.core.state import embedding_service, vector_store

from app.models.document import DocumentResponse
from app.utils.text_extractor import extract_text_from_pdf

router = APIRouter(prefix="/documents", tags=["documents"])

STORAGE_DIR = Path("storage/documents")
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

@router.post("/upload", response_model=DocumentResponse)
async def upload_document(file: UploadFile = File(...)):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files supported")

    doc_id = str(uuid.uuid4())
    file_path = STORAGE_DIR / f"{doc_id}_{file.filename}"

    with open(file_path, "wb") as f:
        f.write(await file.read())

    text = extract_text_from_pdf(str(file_path))
    chunks = chunk_text(text)

    chunk_objects = []
    for i, chunk in enumerate(chunks):
        chunk_objects.append(
            Chunk(
                id=f"{doc_id}_{i}",
                document_id=doc_id,
                text=chunk,
                index=i
            )
        )

    chunk_texts = [c.text for c in chunk_objects]
    embeddings = embedding_service.embed_texts(chunk_texts)

    metadatas = [
        {
            "document_id": doc_id,
            "chunk_index": c.index,
            "filename": file.filename
        }
        for c in chunk_objects
    ]

    vector_store.add(
        embeddings=embeddings,
        texts=chunk_texts,
        metadatas=metadatas
    )

    return DocumentResponse(
    id=doc_id,
    filename=file.filename,
    text_length=len(text),
    chunks=len(chunk_objects),
    created_at=datetime.now()
    )

