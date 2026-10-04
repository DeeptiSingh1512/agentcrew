import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.agents.graph import run as run_crew  # noqa: E402
from app.ingest.pipeline import close_client  # noqa: E402
from app.llm import calls_used, generate, reset_budget  # noqa: E402
from app.rag import PROMPT  # noqa: E402
from app.tools.retriever import search  # noqa: E402

QUESTIONS = ROOT / "eval" / "questions.json"
RESULTS = ROOT / "eval" / "results.json"
SUMMARY = ROOT / "eval" / "results.md"
PAUSE = 5  # seconds between questions, to stay within free-tier limits

REFUSAL = (
    "couldn't find", "could not find", "not found", "no information",
    "not mentioned", "does not mention", "doesn't mention", "not provided",
    "not listed", "no mention", "not specified", "does not contain",
    "not contain", "not included", "no evidence",
)
CITATION = re.compile(r"\[[^\]]+ p\.\d+\]|\[web: [^\]]+\]")


def single(question):
    reset_budget()
    t0 = time.time()
    chunks = search(question, 5)
    context = "\n\n".join(f"[{c['file']} p.{c['page']}]\n{c['text']}" for c in chunks)
    answer = generate(PROMPT.format(context=context, question=question))
    return answer, time.time() - t0, calls_used()


def crew(question):
    reset_budget()
    t0 = time.time()
    out = run_crew(question, plan=[{"q": question, "source": "docs"}])
    return out["report"], time.time() - t0, calls_used(), out["drafts"]


def judge(item, answer):
    text = answer.lower()
    if item["answerable"]:
        return all(k.lower() in text for k in item["must_include"])
    return any(p in text for p in REFUSAL)


def pct(x, n):
    return f"{100 * x / n:.0f}%" if n else "n/a"


def summarize(items, results):
    done = [(i, results[i["question"]]) for i in items if i["question"] in results]
    if not done:
        print("No results yet.")
        return
    rows = []
    for mode, name in (("single", "Single agent"), ("crew", "AgentCrew")):
        ans = [r[mode] for i, r in done if i["answerable"]]
        una = [r[mode] for i, r in done if not i["answerable"]]
        allr = ans + una
        rows.append(
            (
                name,
                pct(sum(r["ok"] for r in ans), len(ans)),
                pct(sum(r["ok"] for r in una), len(una)),
                pct(sum(r["cited"] for r in ans), len(ans)),
                f"{sum(r['seconds'] for r in allr) / len(allr):.1f}",
                f"{sum(r['calls'] for r in allr) / len(allr):.1f}",
            )
        )
    lines = [
        "| Mode | Answer accuracy | Correct refusals | Citation rate | Avg seconds | Avg model calls |",
        "|---|---|---|---|---|---|",
    ]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    text = f"Evaluated {len(done)} of {len(items)} questions\n\n" + "\n".join(lines)
    print("\n" + text)
    SUMMARY.write_text(text + "\n", encoding="utf-8")


def main():
    items = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    results = json.loads(RESULTS.read_text(encoding="utf-8")) if RESULTS.exists() else {}
    try:
        for n, item in enumerate(items, 1):
            q = item["question"]
            if q in results:
                continue  # already done: lets you resume after a Gemini outage
            print(f"[{n}/{len(items)}] {q}", flush=True)
            try:
                s_ans, s_t, s_c = single(q)
                c_ans, c_t, c_c, drafts = crew(q)
            except Exception as e:
                print("  skipped (rerun to retry):", str(e)[:150])
                continue
            results[q] = {
                "answerable": item["answerable"],
                "single": {
                    "ok": judge(item, s_ans),
                    "cited": bool(CITATION.search(s_ans)),
                    "seconds": round(s_t, 1),
                    "calls": s_c,
                    "answer": s_ans,
                },
                "crew": {
                    "ok": judge(item, c_ans),
                    "cited": bool(CITATION.search(c_ans)),
                    "seconds": round(c_t, 1),
                    "calls": c_c,
                    "drafts": drafts,
                    "answer": c_ans,
                },
            }
            RESULTS.write_text(json.dumps(results, indent=2), encoding="utf-8")
            r = results[q]
            print(
                f"  single ok={r['single']['ok']} {r['single']['seconds']}s | "
                f"crew ok={r['crew']['ok']} {r['crew']['seconds']}s drafts={drafts}",
                flush=True,
            )
            time.sleep(PAUSE)
    finally:
        close_client()
    summarize(items, results)


if __name__ == "__main__":
    main()