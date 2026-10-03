import sys
from app.rag import ask

question = " ".join(sys.argv[1:]) or "What are the main topics in this document?"
result = ask(question)

print("\nANSWER:\n", result["answer"])
print("\nSOURCES:")
for s in result["sources"]:
    print(f"  - {s['file']} p.{s['page']} (score {s['score']})")