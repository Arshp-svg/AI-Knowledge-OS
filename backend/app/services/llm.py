from groq import Groq
from app.core.config import settings

MODEL = "llama-3.3-70b-versatile"

client = Groq(
    api_key=settings.groq_api_key
)

def generate_answer(context: str, question: str) -> str:
    system_prompt = (
        "You are an AI assistant that answers questions strictly using the provided context. "
        "If the answer is not present in the context, say: "
        "'I don't know based on the provided documents.'"
    )

    user_prompt = f"""
Context:
{context}

Question:
{question}
"""

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
        max_tokens=512,
    )

    return response.choices[0].message.content.strip()
