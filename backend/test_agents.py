import sys

from app.agents.graph import run
from app.ingest.pipeline import close_client

goal = " ".join(sys.argv[1:]) or "Summarize the candidate's skills and experience"

try:
    result = run(goal)
    print("\nTRACE:")
    for t in result["trace"]:
        print(f"  [{t['agent']}] {t['message']}")
    print("\nREPORT:\n", result["report"])
    print("\nAPPROVED:", result["approved"], "| drafts:", result["drafts"], "| open issues:", result["issues"])
finally:
    close_client()