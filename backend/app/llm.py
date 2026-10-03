import time
from google import genai

from app.config import GEMINI_API_KEY, GEMINI_MODEL

_client = None

# Primary model first, then fallbacks (names from your models list)
FALLBACK_MODELS = ["gemini-flash-latest", "gemini-3.5-flash", "gemini-3.1-flash-lite"]
TRANSIENT = ("503", "429", "500", "UNAVAILABLE", "RESOURCE_EXHAUSTED", "overloaded")


def generate(prompt: str, attempts_per_model: int = 3) -> str:
    global _client
    if _client is None:
        _client = genai.Client(api_key=GEMINI_API_KEY)

    models = list(dict.fromkeys([GEMINI_MODEL, *FALLBACK_MODELS]))
    last = None
    for model in models:
        for i in range(attempts_per_model):
            try:
                resp = _client.models.generate_content(model=model, contents=prompt)
                return resp.text
            except Exception as e:
                last = e
                if not any(t in str(e) for t in TRANSIENT):
                    break  # not a busy-server error (e.g. 404): try the next model
                time.sleep(3 * 2**i)  # 3s, 6s, 12s
    raise RuntimeError(f"Gemini call failed on all models: {last}")