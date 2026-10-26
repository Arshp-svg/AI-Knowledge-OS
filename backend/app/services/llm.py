from typing import Iterator, List, Dict, Any, Optional
from groq import Groq
from app.core.config import settings

MODEL = "openai/gpt-oss-20b"

client = Groq(
    api_key=settings.groq_api_key
)

def rewrite_query(question: str, history: Optional[List[Dict[str, str]]] = None) -> str:
    """
    Reformulates a follow-up question into an independent, standalone search query
    by resolving conversational pronouns and references from chat history.
    """
    if not history or len(history) < 2:
        return question

    recent_history = history[-4:]  # Last 2 conversation turns
    formatted_history = "\n".join(
        f"{msg.get('role', 'user').capitalize()}: {msg.get('content', '')}"
        for msg in recent_history
        if msg.get("content")
    )

    rewrite_system = (
        "You are an expert search query reformulator. Given a chat history and a follow-up question, "
        "rephrase the follow-up question into a single, self-contained search query that can be understood "
        "without the chat history. Do NOT answer the question; only return the reformulated question."
    )

    user_prompt = f"Chat History:\n{formatted_history}\n\nFollow-up Question: {question}\n\nStandalone Question:"

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": rewrite_system},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
            max_tokens=64,
        )
        standalone = response.choices[0].message.content.strip().strip('"\'')
        return standalone if standalone else question
    except Exception:
        return question


from app.services.guardrails import guardrails_service

def generate_answer_with_usage(
    context: str,
    question: str,
    history: Optional[List[Dict[str, str]]] = None
) -> tuple[str, dict]:
    system_prompt = (
        "You are an AI assistant that answers questions strictly using the provided context. "
        "If the answer is not present in the context, say: "
        "'I don't know based on the provided documents.'"
    )

    messages = [{"role": "system", "content": system_prompt}]

    if history:
        for msg in history[-4:]:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role in ["user", "assistant"] and content:
                messages.append({"role": role, "content": content})

    user_prompt = guardrails_service.build_hardened_prompt(context, question)
    messages.append({"role": "user", "content": user_prompt})

    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=0.2,
        max_tokens=512,
    )

    answer = response.choices[0].message.content.strip()
    usage = {
        "prompt_tokens": getattr(response.usage, "prompt_tokens", len(context + question) // 4) if getattr(response, "usage", None) else len(context + question) // 4,
        "completion_tokens": getattr(response.usage, "completion_tokens", len(answer) // 4) if getattr(response, "usage", None) else len(answer) // 4,
        "total_tokens": getattr(response.usage, "total_tokens", (len(context + question) + len(answer)) // 4) if getattr(response, "usage", None) else (len(context + question) + len(answer)) // 4
    }

    return answer, usage

def generate_answer(
    context: str,
    question: str,
    history: Optional[List[Dict[str, str]]] = None
) -> str:
    ans, _ = generate_answer_with_usage(context, question, history)
    return ans


def stream_answer(
    context: str,
    question: str,
    history: Optional[List[Dict[str, str]]] = None
) -> Iterator[str]:
    """
    Streams tokens from Groq LLM token-by-token for ultra-low TTFT (<400ms).
    """
    system_prompt = (
        "You are an AI assistant that answers questions strictly using the provided context. "
        "If the answer is not present in the context, say: "
        "'I don't know based on the provided documents.'"
    )

    messages = [{"role": "system", "content": system_prompt}]

    if history:
        for msg in history[-4:]:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role in ["user", "assistant"] and content:
                messages.append({"role": role, "content": content})

    user_prompt = guardrails_service.build_hardened_prompt(context, question)
    messages.append({"role": "user", "content": user_prompt})

    stream = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=0.2,
        max_tokens=512,
        stream=True
    )

    for chunk in stream:
        content = chunk.choices[0].delta.content or ""
        if content:
            yield content
