import os
import time
import json
import uuid
import sqlite3
import logging
from typing import Optional, Dict, Any, List
from pathlib import Path
from contextlib import contextmanager

from app.core.config import settings

logger = logging.getLogger(__name__)

# Model cost constants (Groq openai/gpt-oss-20b: $0.05 / 1M prompt, $0.08 / 1M completion)
PROMPT_COST_PER_MILLION = 0.05
COMPLETION_COST_PER_MILLION = 0.08

DB_PATH = Path("storage/telemetry.db")

class SpanContext:
    def __init__(self, name: str, attributes: Optional[Dict[str, Any]] = None):
        self.name = name
        self.attributes = attributes or {}
        self.status = "SUCCESS"
        self.start_time = 0.0
        self.duration_ms = 0.0

    def __enter__(self):
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.duration_ms = round((time.perf_counter() - self.start_time) * 1000, 2)
        if exc_type is not None:
            self.status = "ERROR"
            self.attributes["error"] = str(exc_val)
        return False

    def set_attribute(self, key: str, value: Any):
        self.attributes[key] = value

    def set_status(self, status: str):
        self.status = status

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "attributes": self.attributes
        }


class TraceContext:
    def __init__(
        self,
        name: str,
        trace_id: str,
        input_query: str,
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.name = name
        self.trace_id = trace_id
        self.input_query = input_query
        self.metadata = metadata or {}
        self.status = "RUNNING"
        self.output_answer: Optional[str] = None
        self.start_time = time.perf_counter()
        self.duration_ms = 0.0
        self.spans: List[SpanContext] = []
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0
        self.estimated_cost_usd = 0.0

    @contextmanager
    def span(self, name: str, attributes: Optional[Dict[str, Any]] = None):
        span_ctx = SpanContext(name, attributes)
        self.spans.append(span_ctx)
        with span_ctx:
            yield span_ctx

    def record_generation(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        input_text: str = "",
        output_text: str = ""
    ):
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens
        self.total_tokens = self.prompt_tokens + self.completion_tokens
        self.estimated_cost_usd = round(
            (self.prompt_tokens * PROMPT_COST_PER_MILLION / 1_000_000) +
            (self.completion_tokens * COMPLETION_COST_PER_MILLION / 1_000_000),
            6
        )

    def end(self, output_answer: Optional[str] = None, status: str = "SUCCESS"):
        self.duration_ms = round((time.perf_counter() - self.start_time) * 1000, 2)
        self.output_answer = output_answer
        self.status = status

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "name": self.name,
            "input_query": self.input_query,
            "output_answer": self.output_answer,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "estimated_cost_usd": self.estimated_cost_usd,
            "metadata": self.metadata,
            "spans": [s.to_dict() for s in self.spans]
        }


class TelemetryService:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self.langfuse = None
        self._init_langfuse()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS traces (
                    trace_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    input_query TEXT,
                    output_answer TEXT,
                    status TEXT NOT NULL,
                    duration_ms REAL NOT NULL,
                    prompt_tokens INTEGER DEFAULT 0,
                    completion_tokens INTEGER DEFAULT 0,
                    total_tokens INTEGER DEFAULT 0,
                    estimated_cost_usd REAL DEFAULT 0.0,
                    spans_json TEXT,
                    metadata_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Automated column migration for existing tables
            cols = [row[1] for row in conn.execute("PRAGMA table_info(traces)").fetchall()]
            if "spans_json" not in cols:
                conn.execute("ALTER TABLE traces ADD COLUMN spans_json TEXT")

            conn.execute("""
                CREATE TABLE IF NOT EXISTS spans (
                    span_id TEXT PRIMARY KEY,
                    trace_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    duration_ms REAL NOT NULL,
                    attributes_json TEXT,
                    FOREIGN KEY (trace_id) REFERENCES traces(trace_id)
                )
            """)
            conn.commit()

    def _init_langfuse(self):
        pub = settings.langfuse_public_key
        sec = settings.langfuse_secret_key
        if pub and sec:
            try:
                from langfuse import Langfuse
                self.langfuse = Langfuse(
                    public_key=pub,
                    secret_key=sec,
                    host=settings.langfuse_host
                )
                logger.info("Langfuse cloud exporter initialized.")
            except Exception as exc:
                logger.warning(f"Failed to initialize Langfuse cloud exporter: {exc}")
        else:
            logger.info("Langfuse keys not configured. Operating in high-performance local SQLite telemetry mode.")

    def start_trace(
        self,
        name: str,
        trace_id: Optional[str] = None,
        input_query: str = "",
        metadata: Optional[Dict[str, Any]] = None
    ) -> TraceContext:
        tid = trace_id or str(uuid.uuid4())
        return TraceContext(name=name, trace_id=tid, input_query=input_query, metadata=metadata)

    def save_trace(self, trace_ctx: TraceContext):
        d = trace_ctx.to_dict()
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO traces (
                        trace_id, name, input_query, output_answer, status,
                        duration_ms, prompt_tokens, completion_tokens,
                        total_tokens, estimated_cost_usd, spans_json, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    d["trace_id"],
                    d["name"],
                    d["input_query"],
                    d["output_answer"],
                    d["status"],
                    d["duration_ms"],
                    d["prompt_tokens"],
                    d["completion_tokens"],
                    d["total_tokens"],
                    d["estimated_cost_usd"],
                    json.dumps(d["spans"]),
                    json.dumps(d["metadata"])
                ))

                for s in d["spans"]:
                    conn.execute("""
                        INSERT INTO spans (
                            span_id, trace_id, name, status, duration_ms, attributes_json
                        ) VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        str(uuid.uuid4()),
                        d["trace_id"],
                        s["name"],
                        s["status"],
                        s["duration_ms"],
                        json.dumps(s.get("attributes", {}))
                    ))

                conn.commit()
        except Exception as exc:
            logger.error(f"Failed to persist telemetry trace: {exc}")

        # Send to Langfuse Cloud if available
        if self.langfuse:
            try:
                lf_trace = self.langfuse.trace(
                    id=d["trace_id"],
                    name=d["name"],
                    input=d["input_query"],
                    output=d["output_answer"],
                    metadata=d["metadata"]
                )
                for s in d["spans"]:
                    lf_trace.span(
                        name=s["name"],
                        metadata=s["attributes"],
                        output=s["status"]
                    )
            except Exception as exc:
                logger.warning(f"Error exporting trace to Langfuse: {exc}")

    def get_recent_traces(self, limit: int = 25) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT trace_id, name, status, duration_ms, prompt_tokens,
                       completion_tokens, total_tokens, estimated_cost_usd, created_at
                FROM traces
                ORDER BY created_at DESC, rowid DESC
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def get_trace_by_id(self, trace_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT * FROM traces WHERE trace_id = ?
            """, (trace_id,))
            row = cursor.fetchone()
            if not row:
                return None
            d = dict(row)
            d["spans"] = json.loads(d.get("spans_json") or "[]")
            d["metadata"] = json.loads(d.get("metadata_json") or "{}")
            return d

    def get_stats(self) -> Dict[str, Any]:
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT duration_ms, prompt_tokens, completion_tokens,
                       total_tokens, estimated_cost_usd, status, spans_json
                FROM traces
            """)
            rows = cursor.fetchall()

        if not rows:
            return {
                "total_queries": 0,
                "latency_percentiles_ms": {"p50": 0, "p95": 0, "p99": 0},
                "retrieval_latency_ms": {"p50": 0, "p95": 0},
                "generation_latency_ms": {"p50": 0, "p95": 0},
                "tokens": {"total": 0, "prompt": 0, "completion": 0},
                "total_cost_usd": 0.0,
                "status_breakdown": {}
            }

        total_queries = len(rows)
        durations = sorted([r["duration_ms"] for r in rows])
        prompt_tokens = sum(r["prompt_tokens"] for r in rows)
        completion_tokens = sum(r["completion_tokens"] for r in rows)
        total_tokens = sum(r["total_tokens"] for r in rows)
        total_cost = round(sum(r["estimated_cost_usd"] for r in rows), 6)

        status_breakdown: Dict[str, int] = {}
        retrieval_latencies: List[float] = []
        gen_latencies: List[float] = []

        for r in rows:
            st = r["status"]
            status_breakdown[st] = status_breakdown.get(st, 0) + 1
            spans = json.loads(r["spans_json"] or "[]")
            for s in spans:
                if s.get("name") == "retrieval":
                    retrieval_latencies.append(s.get("duration_ms", 0.0))
                elif s.get("name") in ("llm_generation", "llm_streaming_generation"):
                    gen_latencies.append(s.get("duration_ms", 0.0))

        def percentile(data: List[float], p: float) -> float:
            if not data:
                return 0.0
            data_sorted = sorted(data)
            k = (len(data_sorted) - 1) * (p / 100.0)
            f = int(k)
            c = min(f + 1, len(data_sorted) - 1)
            d0 = data_sorted[f] * (c - k)
            d1 = data_sorted[c] * (k - f)
            return round(d0 + d1, 1)

        return {
            "total_queries": total_queries,
            "latency_percentiles_ms": {
                "p50": percentile(durations, 50),
                "p95": percentile(durations, 95),
                "p99": percentile(durations, 99)
            },
            "retrieval_latency_ms": {
                "p50": percentile(retrieval_latencies, 50),
                "p95": percentile(retrieval_latencies, 95)
            },
            "generation_latency_ms": {
                "p50": percentile(gen_latencies, 50),
                "p95": percentile(gen_latencies, 95)
            },
            "tokens": {
                "total": total_tokens,
                "prompt": prompt_tokens,
                "completion": completion_tokens,
                "avg_tokens_per_query": round(total_tokens / total_queries, 1) if total_queries else 0
            },
            "total_cost_usd": total_cost,
            "status_breakdown": status_breakdown
        }

    get_system_stats = get_stats

# Global singleton
telemetry_service = TelemetryService()
