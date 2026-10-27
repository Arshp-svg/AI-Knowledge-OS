import gc
import uuid
import logging
from pathlib import Path
from datetime import datetime
from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks, status, Request, Depends
from pydantic import BaseModel

from app.core.state import embedding_service, vector_store
from app.models.document import DocumentResponse
from app.utils.text_extractor import extract_pages_from_pdf
from app.utils.chunker import chunk_document_pages
from app.services.document_store import document_store
from app.core.security import limiter, validate_uploaded_file, verify_api_tier

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])

STORAGE_DIR = Path("storage/documents")
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

class DocumentStatusResponse(BaseModel):
    id: str
    filename: str
    status: str
    chunks: int
    text_length: int

def process_document_background(doc_id: str, file_path: str, filename: str):
    """
    Background worker task: extracts text page-by-page, performs recursive chunking
    with page numbers, computes embeddings, and indexes into Qdrant with minimal RAM overhead.
    """
    try:
        pages = extract_pages_from_pdf(file_path)
        if not pages:
            document_store.update_status(doc_id=doc_id, status="FAILED", chunks=0, text_length=0)
            return

        chunks = chunk_document_pages(pages, chunk_size=500, overlap=50)
        # Immediately release extracted pages from memory
        del pages
        gc.collect()

        chunk_texts = [c["text"] for c in chunks]
        embeddings = embedding_service.embed_texts(chunk_texts, batch_size=16)
        now_iso = datetime.utcnow().isoformat()

        metadatas = [
            {
                "document_id": doc_id,
                "chunk_index": c["chunk_index"],
                "page_number": c["page_number"],
                "filename": filename,
                "created_at": now_iso
            }
            for c in chunks
        ]

        # Clean up any existing points for this document to prevent duplicates
        vector_store.delete_by_document_id(doc_id)

        vector_store.add(
            embeddings=embeddings,
            texts=chunk_texts,
            metadatas=metadatas
        )

        total_length = sum(len(c["text"]) for c in chunks)
        document_store.update_status(
            doc_id=doc_id,
            status="INDEXED",
            chunks=len(chunks),
            text_length=total_length
        )

        # Release intermediate structures and trigger GC
        del chunk_texts, embeddings, metadatas, chunks
        gc.collect()

        logger.info(f"Successfully processed document {doc_id}.")
    except Exception as e:
        logger.error(f"Error processing document {doc_id}: {e}", exc_info=True)
        document_store.update_status(doc_id=doc_id, status="FAILED", chunks=0, text_length=0)


@router.get("/", response_model=list[DocumentResponse])
def list_documents():
    return document_store.list_documents()

@router.get("/{doc_id}/status", response_model=DocumentStatusResponse)
def get_document_status(doc_id: str):
    doc = document_store.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return DocumentStatusResponse(
        id=doc["id"],
        filename=doc["filename"],
        status=doc["status"],
        chunks=doc["chunks"],
        text_length=doc["text_length"]
    )

@router.get("/{doc_id}", response_model=DocumentResponse)
def get_document(doc_id: str):
    doc = document_store.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc

@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("10/minute;50/hour")
async def upload_document(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    tier: str = Depends(verify_api_tier)
):
    file_bytes = await file.read()

    # Enforce production validation (size <= 10MB, %PDF- magic bytes, path traversal sanitization)
    clean_filename = validate_uploaded_file(file_bytes, file.filename)

    doc_id = str(uuid.uuid4())
    safe_file_path = STORAGE_DIR / f"{doc_id}_{clean_filename}"

    with open(safe_file_path, "wb") as f:
        f.write(file_bytes)

    # Immediately release raw upload payload from memory
    del file_bytes
    gc.collect()

    # Create initial pending record
    doc_record = document_store.save_document(
        doc_id=doc_id,
        filename=clean_filename,
        text_length=0,
        chunks=0,
        status="PROCESSING",
        created_at=datetime.utcnow().isoformat()
    )

    # Offload extraction & indexing to background worker
    background_tasks.add_task(
        process_document_background,
        doc_id=doc_id,
        file_path=str(safe_file_path),
        filename=clean_filename
    )

    return DocumentResponse(
        id=doc_record["id"],
        filename=doc_record["filename"],
        text_length=doc_record["text_length"],
        chunks=doc_record["chunks"],
        status=doc_record["status"],
        created_at=doc_record["created_at"]
    )

@router.post("/{doc_id}/reindex", response_model=DocumentStatusResponse)
@limiter.limit("10/minute")
def reindex_document(request: Request, doc_id: str, background_tasks: BackgroundTasks):
    doc = document_store.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    file_path = STORAGE_DIR / f"{doc_id}_{doc['filename']}"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Original document file not found on disk")

    document_store.update_status(doc_id=doc_id, status="PROCESSING")
    background_tasks.add_task(
        process_document_background,
        doc_id=doc_id,
        file_path=str(file_path),
        filename=doc["filename"]
    )

    return DocumentStatusResponse(
        id=doc_id,
        filename=doc["filename"],
        status="PROCESSING",
        chunks=doc["chunks"],
        text_length=doc["text_length"]
    )

@router.delete("/{doc_id}")
@limiter.limit("20/minute")
def delete_document(request: Request, doc_id: str):
    vector_store.delete_by_document_id(doc_id)
    document_store.delete_document(doc_id)
    return {"message": f"Document {doc_id} deleted successfully"}


