import io
from pathlib import Path
from typing import Optional, Tuple
from fastapi import Request, HTTPException, status, Header
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings

# Global SlowAPI Rate Limiter
# Uses client IP address to enforce sliding window limits
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["120/minute"]
)

# Security Constants
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB upload ceiling
PDF_MAGIC_BYTES = b"%PDF-"             # Authentic PDF file signature

def validate_uploaded_file(file_bytes: bytes, filename: str) -> str:
    """
    Enforces production file upload security:
    1. Size Quota: Blocks files exceeding 10 MB.
    2. Magic Bytes Inspection: Verifies genuine PDF header (stops renamed executables).
    3. Path Traversal Protection: Sanitizes filename to prevent directory traversal exploits.
    """
    # 1. Size ceiling check
    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum allowed size of {MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB."
        )

    # 2. Authentic PDF magic bytes verification
    if not file_bytes.startswith(PDF_MAGIC_BYTES):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file format. The file is not an authentic PDF document."
        )

    # 3. Path traversal protection: strip any ../ or leading slashes
    clean_filename = Path(filename).name
    if not clean_filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only files with .pdf extension are permitted."
        )

    return clean_filename


def verify_api_tier(x_api_key: Optional[str] = Header(None)) -> str:
    """
    API Key Authentication:
    - If valid admin key provided, assigns 'admin' tier (unlimited quotas).
    - Otherwise assigns 'guest' tier (enforces public sliding-window limits).
    """
    admin_key = getattr(settings, "admin_api_key", None)
    if admin_key and x_api_key == admin_key:
        return "admin"
    return "guest"
