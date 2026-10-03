import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
MONGO_URL = os.getenv("MONGO_URL", "")
QDRANT_PATH = str(ROOT / os.getenv("QDRANT_PATH", "./data/qdrant"))
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")