from pydantic import BaseModel

class Chunk(BaseModel):
    id: str
    document_id: str
    text: str
    index: int
