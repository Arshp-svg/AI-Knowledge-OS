from typing import List
from transformers import AutoTokenizer

tokenizer = AutoTokenizer.from_pretrained(
    "sentence-transformers/all-MiniLM-L6-v2"
)
MIN_CHUNKS = 3 
def count_tokens(text: str) -> int:
    return len(tokenizer.encode(text, add_special_tokens=False))

def chunk_text(
    text: str,
    max_tokens: int = 200,
    overlap_tokens: int = 80
) -> List[str]:
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks = []

    current_chunk = []
    current_tokens = 0

    for paragraph in paragraphs:
        para_tokens = count_tokens(paragraph)

        # Hard split if paragraph is too long
        if para_tokens > max_tokens:
            words = paragraph.split(" ")
            temp = ""
            for word in words:
                if count_tokens(temp + word) > max_tokens:
                    chunks.append(temp.strip())
                    temp = word + " "
                else:
                    temp += word + " "
            if temp.strip():
                chunks.append(temp.strip())
            continue

        if current_tokens + para_tokens <= max_tokens:
            current_chunk.append(paragraph)
            current_tokens += para_tokens
        else:
            chunk_text = "\n\n".join(current_chunk)
            chunks.append(chunk_text)

            # Token-based overlap
            overlap_text = " ".join(chunk_text.split()[-overlap_tokens:])
            current_chunk = [overlap_text, paragraph]
            current_tokens = count_tokens(overlap_text) + para_tokens

    if current_chunk:
        chunks.append("\n\n".join(current_chunk))
    # Ensure minimum chunk count for retrieval quality
    if len(chunks) < MIN_CHUNKS and len(text) > 300:
        mid = len(text) // 2
        chunks = [
            text[:mid],
            text[mid:]
        ]


    return chunks
