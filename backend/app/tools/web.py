from urllib.parse import urlparse

from ddgs import DDGS


def web_search(query: str, k: int = 3):
    """Free web search. Returns [] if the search fails, so the crew keeps going."""
    try:
        results = DDGS().text(query, max_results=k)
    except Exception:
        return []
    out = []
    for r in results or []:
        url = r.get("href", "")
        out.append(
            {
                "label": "web: " + urlparse(url).netloc.replace("www.", ""),
                "url": url,
                "title": r.get("title", ""),
                "text": r.get("body", ""),
            }
        )
    return out