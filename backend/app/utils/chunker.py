from typing import List, Dict, Any

class RecursiveCharacterChunker:
    """
    Splits text recursively using hierarchical separators:
    Paragraphs -> Lines -> Sentences -> Words -> Characters.
    """
    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = ["\n\n", "\n", ". ", "? ", "! ", " ", ""]

    def _split_text(self, text: str, separators: List[str]) -> List[str]:
        final_chunks = []
        separator = separators[-1]
        new_separators = []

        for i, sep in enumerate(separators):
            if sep == "":
                separator = ""
                break
            if sep in text:
                separator = sep
                new_separators = separators[i + 1:]
                break

        splits = text.split(separator) if separator else list(text)

        good_splits = []
        for s in splits:
            if not s:
                continue
            if len(s) < self.chunk_size:
                good_splits.append(s)
            else:
                if new_separators:
                    sub_splits = self._split_text(s, new_separators)
                    good_splits.extend(sub_splits)
                else:
                    good_splits.append(s)

        # Merge splits with overlap
        current_chunk = ""
        for s in good_splits:
            candidate = f"{current_chunk}{separator}{s}" if current_chunk else s
            if len(candidate) <= self.chunk_size:
                current_chunk = candidate
            else:
                if current_chunk.strip():
                    final_chunks.append(current_chunk.strip())
                # Overlap retention
                if self.chunk_overlap > 0 and len(current_chunk) > self.chunk_overlap:
                    overlap_seed = current_chunk[-self.chunk_overlap:]
                    current_chunk = f"{overlap_seed}{separator}{s}".strip()
                else:
                    current_chunk = s

        if current_chunk.strip():
            final_chunks.append(current_chunk.strip())

        return final_chunks

    def split_text(self, text: str) -> List[str]:
        if not text.strip():
            return []
        return self._split_text(text, self.separators)

    def split_pages(self, pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Chunks page objects while preserving page_number metadata.
        """
        all_chunks = []
        global_idx = 0

        for page in pages:
            page_num = page.get("page_number", 1)
            page_text = page.get("text", "")
            raw_chunks = self.split_text(page_text)

            for chunk_str in raw_chunks:
                if len(chunk_str.strip()) < 20:
                    continue
                all_chunks.append({
                    "chunk_index": global_idx,
                    "page_number": page_num,
                    "text": chunk_str
                })
                global_idx += 1

        return all_chunks

# Global instance with optimal defaults
default_chunker = RecursiveCharacterChunker(chunk_size=500, chunk_overlap=50)

def chunk_text(text: str, max_tokens: int = 500, overlap_tokens: int = 50) -> List[str]:
    """
    Backwards-compatible wrapper.
    """
    chunker = RecursiveCharacterChunker(chunk_size=max_tokens, chunk_overlap=overlap_tokens)
    return chunker.split_text(text)

def chunk_document_pages(pages: List[Dict[str, Any]], chunk_size: int = 500, overlap: int = 50) -> List[Dict[str, Any]]:
    chunker = RecursiveCharacterChunker(chunk_size=chunk_size, chunk_overlap=overlap)
    return chunker.split_pages(pages)
