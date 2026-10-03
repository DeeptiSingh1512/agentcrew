from app.ingest.pipeline import COLLECTION, get_client, get_embedder


def search(query: str, k: int = 5):
    """Return the top-k most similar chunks for a question."""
    vector = next(iter(get_embedder().query_embed(query))).tolist()
    result = get_client().query_points(COLLECTION, query=vector, limit=k)
    return [
        {
            "file": p.payload["file"],
            "page": p.payload["page"],
            "text": p.payload["text"],
            "score": round(p.score, 3),
        }
        for p in result.points
    ]