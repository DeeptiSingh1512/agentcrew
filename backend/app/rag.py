import time
from google import genai

from app.config import GEMINI_API_KEY, GEMINI_MODEL
from app.tools.retriever import search

_llm = None

PROMPT = """You are a careful assistant. Answer the question using ONLY the context below.
- After each claim, cite its source like [file p.3].
- If the context does not contain the answer, reply exactly:
  "I couldn't find this in the uploaded documents."
- Do not use outside knowledge.

CONTEXT:
{context}

QUESTION: {question}
"""


def get_llm():
    global _llm
    if _llm is None:
        _llm = genai.Client(api_key=GEMINI_API_KEY)
    return _llm


def ask(question: str, k: int = 5):
    chunks = search(question, k)
    context = "\n\n".join(
        f"[{c['file']} p.{c['page']}]\n{c['text']}" for c in chunks
    )
    prompt = PROMPT.format(context=context, question=question)

    last_error = None
    for attempt in range(3):  # retry on free-tier rate limits / busy server
        try:
            resp = get_llm().models.generate_content(model=GEMINI_MODEL, contents=prompt)
            return {"answer": resp.text, "sources": chunks}
        except Exception as e:
            last_error = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Gemini call failed: {last_error}")