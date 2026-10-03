import uuid

import pymupdf
from fastembed import TextEmbedding
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PointStruct,
    VectorParams,
)

from app.config import QDRANT_PATH

COLLECTION = "documents"
CHUNK_SIZE = 1500  # characters per chunk
OVERLAP = 200  # characters shared between chunks

_embedder = None
_client = None


def get_embedder():
    global _embedder
    if _embedder is None:
        _embedder = TextEmbedding("BAAI/bge-small-en-v1.5")
    return _embedder


def get_client():
    global _client
    if _client is None:
        _client = QdrantClient(path=QDRANT_PATH)
        if not _client.collection_exists(COLLECTION):
            _client.create_collection(
                COLLECTION,
                vectors_config=VectorParams(size=384, distance=Distance.COSINE),
            )
    return _client


def close_client():
    """Close the Qdrant client cleanly (used on server shutdown)."""
    global _client
    if _client is not None:
        _client.close()
        _client = None


def extract_pages(path):
    """Return a list of (page_number, text) for a PDF."""
    doc = pymupdf.open(path)
    pages = []
    for i, page in enumerate(doc, start=1):
        text = page.get_text().strip()
        if text:
            pages.append((i, text))
    return pages


def chunk_text(text):
    chunks = []
    start = 0
    while start < len(text):
        chunks.append(text[start:start + CHUNK_SIZE])
        start += CHUNK_SIZE - OVERLAP
    return chunks


def delete_file(filename: str):
    """Remove all stored chunks of a file, so re-uploading replaces it."""
    get_client().delete(
        COLLECTION,
        points_selector=FilterSelector(
            filter=Filter(
                must=[FieldCondition(key="file", match=MatchValue(value=filename))]
            )
        ),
    )


def ingest_pdf(path, filename):
    """Extract, chunk, embed, and store a PDF. Returns the number of chunks."""
    texts, metas = [], []
    for page_no, page_text in extract_pages(path):
        for chunk in chunk_text(page_text):
            texts.append(chunk)
            metas.append({"file": filename, "page": page_no, "text": chunk})

    if not texts:
        return 0

    vectors = [v.tolist() for v in get_embedder().embed(texts)]
    points = [
        PointStruct(id=str(uuid.uuid4()), vector=vec, payload=meta)
        for vec, meta in zip(vectors, metas)
    ]
    delete_file(filename)  # re-uploading the same file replaces the old chunks
    get_client().upsert(COLLECTION, points)
    return len(points)