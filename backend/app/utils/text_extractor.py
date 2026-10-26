from typing import List, Dict, Any
from pypdf import PdfReader

def extract_pages_from_pdf(file_path: str) -> List[Dict[str, Any]]:
    """
    Extracts text page-by-page from a PDF, preserving page numbers for citation tracking.
    """
    reader = PdfReader(file_path)
    pages = []

    for idx, page in enumerate(reader.pages):
        page_text = page.extract_text()
        if page_text and page_text.strip():
            pages.append({
                "page_number": idx + 1,
                "text": page_text.strip()
            })

    return pages

def extract_text_from_pdf(file_path: str) -> str:
    """
    Backwards-compatible helper returning all text joined.
    """
    pages = extract_pages_from_pdf(file_path)
    return "\n\n".join(p["text"] for p in pages)
