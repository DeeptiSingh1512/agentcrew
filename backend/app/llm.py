import threading
import time

from google import genai

from app.config import GEMINI_API_KEY, GEMINI_MODEL

_client = None

# Primary model first, then fallbacks (names from your models list)
FALLBACK_MODELS = [
    "gemini-flash-latest",
    "gemini-3.5-flash",
    "gemini-3.6-flash",
    "gemini-3.7-flash",
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
]
TRANSIENT = ("503", "429", "500", "UNAVAILABLE", "RESOURCE_EXHAUSTED", "overloaded")

# Guardrail: maximum model calls in one crew run
MAX_CALLS_PER_RUN = 12
_lock = threading.Lock()
_calls = 0


class BudgetExceeded(RuntimeError):
    pass


def reset_budget():
    global _calls
    with _lock:
        _calls = 0


def _spend():
    global _calls
    with _lock:
        _calls += 1
        if _calls > MAX_CALLS_PER_RUN:
            raise BudgetExceeded(
                f"Stopped: this run needed more than {MAX_CALLS_PER_RUN} model calls"
            )


def generate(prompt: str, rounds: int = 2, attempts_per_model: int = 2) -> str:
    global _client
    _spend()  # counts once per logical call, not per retry
    if _client is None:
        _client = genai.Client(api_key=GEMINI_API_KEY)

    models = list(dict.fromkeys([GEMINI_MODEL, *FALLBACK_MODELS]))
    last = None
    for r in range(rounds):
        for model in models:
            for i in range(attempts_per_model):
                try:
                    resp = _client.models.generate_content(model=model, contents=prompt)
                    return resp.text
                except Exception as e:
                    last = e
                    if not any(t in str(e) for t in TRANSIENT):
                        break  # not a busy-server error: try the next model
                    time.sleep(2 * (i + 1))
        if r < rounds - 1:
            time.sleep(20)  # everything was busy: wait, then try the whole list again
    raise RuntimeError(f"Gemini call failed on all models: {last}")

def calls_used():
    return _calls