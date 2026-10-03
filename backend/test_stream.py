import json
import sys

import httpx

goal = " ".join(sys.argv[1:]) or "Summarize the skills and work experience"

with httpx.stream("POST", "http://localhost:8000/run", json={"goal": goal}, timeout=600) as r:
    for line in r.iter_lines():
        if not line.startswith("data: "):
            continue
        event = json.loads(line[6:])
        if event["type"] == "step":
            print(f"[{event['agent']}] {event['message']}", flush=True)
        elif event["type"] == "done":
            print("\nREPORT:\n", event["report"])
            print("\nAPPROVED:", event["approved"], "| drafts:", event["drafts"])
        else:
            print("ERROR:", event)