import time
from google import genai

from app.config import GEMINI_API_KEY, GEMINI_MODEL

_client = None


def generate(prompt: str, retries: int = 3) -> str:
    global _client
    if _client is None:
        _client = genai.Client(api_key=GEMINI_API_KEY)
    last = None
    for i in range(retries):
        try:
            resp = _client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
            return resp.text
        except Exception as e:
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"Gemini call failed: {last}")