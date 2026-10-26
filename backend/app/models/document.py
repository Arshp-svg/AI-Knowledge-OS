from pydantic import BaseModel
from datetime import datetime

class DocumentCreate(BaseModel):
    filename: str

class DocumentResponse(BaseModel):
    id: str
    filename: str
    text_length: int
    created_at: datetime
    chunks: int
    status: str = "INDEXED"
