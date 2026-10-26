import json
import uuid
from typing import List, Dict, Optional
from fastapi import APIRouter, Request, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.state import hybrid_retriever
from app.services.llm import generate_answer_with_usage, stream_answer, rewrite_query
from app.services.guardrails import guardrails_service
from app.core.security import limiter, verify_api_tier
from app.core.telemetry import telemetry_service

router = APIRouter(prefix="/ask", tags=["ask"])

class ChatMessage(BaseModel):
    role: str
    content: str

class AskRequest(BaseModel):
    question: str
    top_k: int = 4
    history: Optional[List[ChatMessage]] = []

def format_context(retrieved_chunks: list) -> str:
    return "\n\n".join(
        f"[Source {i+1} | {chunk['metadata'].get('filename', 'Doc')} (Page {chunk['metadata'].get('page_number', 1)}) | Score: {chunk.get('score', 0.0)}]\n{chunk['text']}"
        for i, chunk in enumerate(retrieved_chunks)
    )

@router.post("/")
@limiter.limit("20/minute")
def ask_question(
    request: Request,
    body: AskRequest,
    tier: str = Depends(verify_api_tier)
):
    trace_id = getattr(request.state, "trace_id", str(uuid.uuid4()))
    trace_ctx = telemetry_service.start_trace(
        name="rag_query",
        trace_id=trace_id,
        input_query=body.question,
        metadata={"tier": tier, "top_k": body.top_k, "stream": False}
    )

    try:
        # Span 1: Guardrails (Prompt Injection Defense & PII Redaction)
        with trace_ctx.span("guardrails", {"query_length": len(body.question)}) as span:
            is_injection, _ = guardrails_service.detect_prompt_injection(body.question)
            if is_injection:
                span.set_attribute("injection_detected", True)
                span.set_status("BLOCKED")
                alert_msg = "⚠️ Security Alert: Potential prompt injection or system override detected. This query was blocked by AI Guardrails."
                trace_ctx.end(output_answer=alert_msg, status="GUARDRAIL_BLOCKED")
                telemetry_service.save_trace(trace_ctx)
                return {
                    "question": body.question,
                    "answer": alert_msg,
                    "sources": [],
                    "guardrails_flagged": True,
                    "trace_id": trace_id
                }

            sanitized_question, scrubbed_pii = guardrails_service.scrub_pii(body.question)
            span.set_attribute("pii_redacted", scrubbed_pii)

        history_dicts = [{"role": m.role, "content": m.content} for m in body.history] if body.history else []
        standalone_query = sanitized_question

        # Span 2: Conversational Query Rewriting (if history present)
        if history_dicts:
            with trace_ctx.span("query_rewriting", {"history_turns": len(history_dicts)}) as span:
                standalone_query = rewrite_query(sanitized_question, history_dicts)
                span.set_attribute("standalone_query", standalone_query)

        # Span 3: Hybrid Retrieval (Dense Qdrant + Sparse BM25 + FlashRank Reranker)
        with trace_ctx.span("retrieval", {"top_k": body.top_k, "query": standalone_query}) as span:
            retrieved_chunks = hybrid_retriever.search(
                query=standalone_query,
                top_k=body.top_k
            )
            span.set_attribute("retrieved_chunks_count", len(retrieved_chunks))

        # Span 4: Grounding Boundary Check
        with trace_ctx.span("grounding_boundary_check") as span:
            is_relevant, max_score = guardrails_service.check_retrieval_relevance(retrieved_chunks)
            span.set_attribute("is_relevant", is_relevant)
            span.set_attribute("max_score", max_score)

        if not is_relevant:
            notice = f"I couldn't find sufficient information in your uploaded documents to answer this question accurately. (Top document relevance score: {round(max_score * 100)}%, which is below the required confidence threshold)."
            trace_ctx.end(output_answer=notice, status="GROUNDING_REJECTED")
            telemetry_service.save_trace(trace_ctx)
            return {
                "question": body.question,
                "standalone_query": standalone_query,
                "answer": notice,
                "sources": [],
                "pii_redacted": scrubbed_pii,
                "trace_id": trace_id
            }

        context = format_context(retrieved_chunks)

        # Span 5: LLM Generation
        with trace_ctx.span("llm_generation") as span:
            answer, usage = generate_answer_with_usage(
                context=context,
                question=sanitized_question,
                history=history_dicts
            )
            span.set_attribute("prompt_tokens", usage["prompt_tokens"])
            span.set_attribute("completion_tokens", usage["completion_tokens"])
            span.set_attribute("total_tokens", usage["total_tokens"])

            trace_ctx.record_generation(
                model="openai/gpt-oss-20b",
                prompt_tokens=usage["prompt_tokens"],
                completion_tokens=usage["completion_tokens"],
                input_text=sanitized_question,
                output_text=answer
            )

        trace_ctx.end(output_answer=answer, status="SUCCESS")
        telemetry_service.save_trace(trace_ctx)

        return {
            "question": body.question,
            "standalone_query": standalone_query,
            "answer": answer,
            "sources": retrieved_chunks,
            "pii_redacted": scrubbed_pii,
            "trace_id": trace_id
        }

    except Exception as exc:
        trace_ctx.end(output_answer=str(exc), status="ERROR")
        telemetry_service.save_trace(trace_ctx)
        raise

@router.post("/stream")
@limiter.limit("15/minute")
def ask_question_stream(
    request: Request,
    body: AskRequest,
    tier: str = Depends(verify_api_tier)
):
    trace_id = getattr(request.state, "trace_id", str(uuid.uuid4()))
    trace_ctx = telemetry_service.start_trace(
        name="rag_stream_query",
        trace_id=trace_id,
        input_query=body.question,
        metadata={"tier": tier, "top_k": body.top_k, "stream": True}
    )

    # Span 1: Guardrails Check
    with trace_ctx.span("guardrails", {"query_length": len(body.question)}) as span:
        is_injection, _ = guardrails_service.detect_prompt_injection(body.question)
        if is_injection:
            span.set_attribute("injection_detected", True)
            span.set_status("BLOCKED")
            alert_msg = "⚠️ Security Alert: Potential prompt injection or system override detected. This query was blocked by AI Guardrails."
            trace_ctx.end(output_answer=alert_msg, status="GUARDRAIL_BLOCKED")
            telemetry_service.save_trace(trace_ctx)

            def injection_stream():
                yield f"data: {json.dumps({'type': 'metadata', 'sources': [], 'trace_id': trace_id})}\n\n"
                yield f"data: {json.dumps({'type': 'token', 'token': alert_msg})}\n\n"
                yield f"data: {json.dumps({'type': 'done'})}\n\n"

            return StreamingResponse(injection_stream(), media_type="text/event-stream")

        sanitized_question, scrubbed_pii = guardrails_service.scrub_pii(body.question)
        span.set_attribute("pii_redacted", scrubbed_pii)

    history_dicts = [{"role": m.role, "content": m.content} for m in body.history] if body.history else []
    standalone_query = sanitized_question

    # Span 2: Conversational Query Rewriter
    if history_dicts:
        with trace_ctx.span("query_rewriting") as span:
            standalone_query = rewrite_query(sanitized_question, history_dicts)
            span.set_attribute("standalone_query", standalone_query)

    # Span 3: Hybrid Retrieval
    with trace_ctx.span("retrieval", {"top_k": body.top_k}) as span:
        retrieved_chunks = hybrid_retriever.search(
            query=standalone_query,
            top_k=body.top_k
        )
        span.set_attribute("retrieved_chunks_count", len(retrieved_chunks))

    # Span 4: Grounding Boundary Check
    with trace_ctx.span("grounding_boundary_check") as span:
        is_relevant, max_score = guardrails_service.check_retrieval_relevance(retrieved_chunks)
        span.set_attribute("is_relevant", is_relevant)
        span.set_attribute("max_score", max_score)

    def event_stream():
        # First event: Send sources metadata and trace_id
        metadata_payload = {
            "type": "metadata",
            "standalone_query": standalone_query,
            "sources": retrieved_chunks if is_relevant else [],
            "pii_redacted": scrubbed_pii,
            "trace_id": trace_id
        }
        yield f"data: {json.dumps(metadata_payload)}\n\n"

        if not is_relevant:
            notice = f"I couldn't find sufficient information in your uploaded documents to answer this question accurately. (Top document relevance score: {round(max_score * 100)}%, which is below the required confidence threshold)."
            trace_ctx.end(output_answer=notice, status="GROUNDING_REJECTED")
            telemetry_service.save_trace(trace_ctx)
            yield f"data: {json.dumps({'type': 'token', 'token': notice})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return

        context = format_context(retrieved_chunks)
        accumulated_tokens = []

        # Stream token chunks from LLM
        with trace_ctx.span("llm_streaming_generation") as span:
            for token in stream_answer(context=context, question=sanitized_question, history=history_dicts):
                accumulated_tokens.append(token)
                token_payload = {
                    "type": "token",
                    "token": token
                }
                yield f"data: {json.dumps(token_payload)}\n\n"

            full_answer = "".join(accumulated_tokens)
            prompt_token_est = len(context + sanitized_question) // 4
            completion_token_est = len(accumulated_tokens)

            span.set_attribute("prompt_tokens_est", prompt_token_est)
            span.set_attribute("completion_tokens_est", completion_token_est)

            trace_ctx.record_generation(
                model="openai/gpt-oss-20b",
                prompt_tokens=prompt_token_est,
                completion_tokens=completion_token_est,
                input_text=sanitized_question,
                output_text=full_answer
            )

        trace_ctx.end(output_answer="".join(accumulated_tokens), status="SUCCESS")
        telemetry_service.save_trace(trace_ctx)

        # Final event: Signal completion
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream",
            "X-Trace-ID": trace_id
        }
    )
