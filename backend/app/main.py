from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from app.routes_run import router as run_router

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.config import ROOT
from app.ingest.pipeline import close_client, ingest_pdf
from app.rag import ask

MAX_UPLOAD_BYTES = 10 * 1024 * 1024


class HealthResponse(BaseModel):
	status: str


class UploadResponse(BaseModel):
	filename: str
	chunks: int


class AskRequest(BaseModel):
	question: str
	k: int = 5


class AskResponse(BaseModel):
	answer: str
	sources: list[dict[str, Any]]


@asynccontextmanager
async def lifespan(_: FastAPI):
	yield
	close_client()


app = FastAPI(lifespan=lifespan)
app.include_router(run_router)
app.add_middleware(
	CORSMiddleware,
	allow_origins=["http://localhost:5173"],
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
def health():
	return {"status": "ok"}


@app.post("/upload", response_model=UploadResponse)
def upload_pdf(file: UploadFile = File(...)):
	filename = Path(file.filename or "").name
	if not filename.lower().endswith(".pdf"):
		raise HTTPException(status_code=415, detail="Only PDF files are accepted.")

	contents = file.file.read(MAX_UPLOAD_BYTES + 1)
	if len(contents) > MAX_UPLOAD_BYTES:
		raise HTTPException(status_code=413, detail="PDF files must not exceed 10 MB.")
	if b"%PDF-" not in contents[:1024]:
		raise HTTPException(status_code=415, detail="The uploaded file is not a valid PDF.")

	upload_dir = ROOT / "data" / "uploads"
	upload_dir.mkdir(parents=True, exist_ok=True)
	saved_path = upload_dir / filename
	saved_path.write_bytes(contents)
	return {"filename": filename, "chunks": ingest_pdf(str(saved_path), filename)}


@app.post("/ask", response_model=AskResponse)
def answer_question(request: AskRequest):
	question = request.question.strip()
	if not question:
		raise HTTPException(status_code=422, detail="Question must not be empty.")
	try:
		return ask(question, request.k)
	except RuntimeError as exc:
		raise HTTPException(status_code=502, detail=f"Gemini request failed: {exc}") from exc
