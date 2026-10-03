import json
import re
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.llm import generate
from app.tools.retriever import search


class State(TypedDict):
    goal: str
    plan: list[str]
    evidence: list[dict]
    report: str
    trace: list[dict]


def _log(state, agent, message):
    return state["trace"] + [{"agent": agent, "message": message}]


PLAN_PROMPT = """Break the goal into 2 to 4 short, specific questions that can be
answered by searching the uploaded documents.
Return ONLY a JSON array of strings, with no other text.

GOAL: {goal}"""

WRITE_PROMPT = """Write a clear report that achieves the goal, using ONLY the evidence below.
- Cite each claim like [file p.3].
- If the evidence is not enough, say what is missing. Do not invent facts.

GOAL: {goal}

EVIDENCE:
{evidence}
"""


def planner(state: State):
    raw = generate(PLAN_PROMPT.format(goal=state["goal"]))
    try:
        match = re.search(r"\[.*\]", raw, re.S)
        plan = [str(q) for q in json.loads(match.group(0))][:4]
    except Exception:
        plan = [state["goal"]]  # fallback if the model returns bad JSON
    return {
        "plan": plan,
        "trace": _log(state, "planner", f"Created {len(plan)} sub-questions: {plan}"),
    }


def retriever(state: State):
    seen, unique = set(), []
    for q in state["plan"]:
        for c in search(q, k=3):
            key = (c["file"], c["page"], c["text"][:80])
            if key not in seen:
                seen.add(key)
                unique.append({**c, "question": q})
    return {
        "evidence": unique,
        "trace": _log(state, "retriever", f"Found {len(unique)} unique passages"),
    }


def writer(state: State):
    evidence = "\n\n".join(
        f"[{e['file']} p.{e['page']}] {e['text']}" for e in state["evidence"]
    )
    report = generate(WRITE_PROMPT.format(goal=state["goal"], evidence=evidence))
    return {"report": report, "trace": _log(state, "writer", "Drafted the report")}


def build_graph():
    g = StateGraph(State)
    g.add_node("planner", planner)
    g.add_node("retriever", retriever)
    g.add_node("writer", writer)
    g.add_edge(START, "planner")
    g.add_edge("planner", "retriever")
    g.add_edge("retriever", "writer")
    g.add_edge("writer", END)
    return g.compile()


def run(goal: str):
    return build_graph().invoke(
        {"goal": goal, "plan": [], "evidence": [], "report": "", "trace": []}
    )