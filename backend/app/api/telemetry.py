from fastapi import APIRouter, HTTPException, Request
from app.core.telemetry import telemetry_service
from app.core.security import limiter

router = APIRouter(prefix="/telemetry", tags=["telemetry"])

@router.get("/traces")
@limiter.limit("60/minute")
def get_recent_traces(request: Request, limit: int = 25):
    """
    Returns recent end-to-end query traces with child spans,
    latency breakdowns, token usages, and cost estimations.
    """
    return {
        "traces": telemetry_service.get_recent_traces(limit=limit)
    }

@router.get("/traces/{trace_id}")
@limiter.limit("60/minute")
def get_trace_detail(request: Request, trace_id: str):
    """
    Returns full trace waterfall details for a given trace_id or request_id.
    """
    trace = telemetry_service.get_trace_by_id(trace_id)
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found")
    return trace

@router.get("/stats")
@limiter.limit("60/minute")
def get_telemetry_stats(request: Request):
    """
    Returns aggregated P50, P95, P99 latency percentiles,
    token consumption metrics, and estimated LLM costs.
    """
    return telemetry_service.get_system_stats()
