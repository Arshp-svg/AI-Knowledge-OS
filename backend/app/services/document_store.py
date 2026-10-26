import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any

DB_PATH = Path("storage/metadata.db")

class DocumentStore:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    text_length INTEGER DEFAULT 0,
                    chunks INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'INDEXED',
                    created_at TEXT NOT NULL
                )
            """)
            conn.commit()

    def save_document(
        self,
        doc_id: str,
        filename: str,
        text_length: int,
        chunks: int,
        status: str = "INDEXED",
        created_at: Optional[str] = None
    ) -> Dict[str, Any]:
        if not created_at:
            created_at = datetime.utcnow().isoformat()
            
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO documents (id, filename, text_length, chunks, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (doc_id, filename, text_length, chunks, status, created_at))
            conn.commit()

        return {
            "id": doc_id,
            "filename": filename,
            "text_length": text_length,
            "chunks": chunks,
            "status": status,
            "created_at": created_at
        }

    def list_documents(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM documents ORDER BY created_at DESC")
            return [dict(row) for row in cursor.fetchall()]

    def get_document(self, doc_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def update_status(
        self,
        doc_id: str,
        status: str,
        chunks: Optional[int] = None,
        text_length: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            if chunks is not None and text_length is not None:
                conn.execute("""
                    UPDATE documents 
                    SET status = ?, chunks = ?, text_length = ?
                    WHERE id = ?
                """, (status, chunks, text_length, doc_id))
            else:
                conn.execute("""
                    UPDATE documents 
                    SET status = ?
                    WHERE id = ?
                """, (status, doc_id))
            conn.commit()

        return self.get_document(doc_id)

    def delete_document(self, doc_id: str) -> bool:
        with self._get_connection() as conn:
            conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
            conn.commit()
        return True

    def check_health(self) -> dict:
        try:
            with self._get_connection() as conn:
                cursor = conn.execute("SELECT count(*) as count FROM documents")
                row = cursor.fetchone()
                doc_count = row["count"] if row else 0
            return {
                "status": "healthy",
                "document_count": doc_count,
                "db_path": str(self.db_path)
            }
        except Exception as exc:
            return {
                "status": "unhealthy",
                "error": str(exc),
                "db_path": str(self.db_path)
            }

# Singleton instance
document_store = DocumentStore()

