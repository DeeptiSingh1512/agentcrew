import json
import re
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.llm import generate
from app.tools.retriever import search

MAX_DRAFTS = 3  # guardrail: the writer/critic loop stops after this many drafts


class State(TypedDict):
    goal: str
    plan: list[str]
    evidence: list[dict]
    report: str
    issues: list[str]
    approved: bool
    drafts: int
    trace: list[dict]


def _log(state, agent, message):
    return state["trace"] + [{"agent": agent, "message": message}]


def _evidence_text(state):
    return "\n\n".join(
        f"[{e['file']} p.{e['page']}] {e['text']}" for e in state["evidence"]
    )


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

REVISE_PROMPT = """Revise the report below to fix every issue listed.
Use ONLY the evidence. Cite each claim like [file p.3]. Do not invent facts.
Return only the corrected report.

GOAL: {goal}

EVIDENCE:
{evidence}

CURRENT REPORT:
{report}

ISSUES TO FIX:
{issues}
"""

CRITIC_PROMPT = """You are a strict reviewer. Check the REPORT against the EVIDENCE.
Look for: claims not supported by the evidence, wrong or missing citations,
malformed citations (they must look like [file p.3]), and important gaps.
Return ONLY JSON with two keys: "approved" (true or false) and
"issues" (a list of at most 5 short strings; empty if approved).

EVIDENCE:
{evidence}

REPORT:
{report}
"""


def planner(state: State):
    raw = generate(PLAN_PROMPT.format(goal=state["goal"]))
    try:
        match = re.search(r"\[.*\]", raw, re.S)
        plan = [str(q) for q in json.loads(match.group(0))][:4]
    except Exception:
        plan = [state["goal"]]
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
    evidence = _evidence_text(state)
    if state["issues"]:
        prompt = REVISE_PROMPT.format(
            goal=state["goal"],
            evidence=evidence,
            report=state["report"],
            issues="\n".join(f"- {i}" for i in state["issues"]),
        )
        msg = f"Revised the report (draft {state['drafts'] + 1}) to fix {len(state['issues'])} issues"
    else:
        prompt = WRITE_PROMPT.format(goal=state["goal"], evidence=evidence)
        msg = "Drafted the report"
    report = generate(prompt)
    return {
        "report": report,
        "drafts": state["drafts"] + 1,
        "trace": _log(state, "writer", msg),
    }


def critic(state: State):
    raw = generate(
        CRITIC_PROMPT.format(evidence=_evidence_text(state), report=state["report"])
    )
    try:
        match = re.search(r"\{.*\}", raw, re.S)
        data = json.loads(match.group(0))
        approved = bool(data.get("approved"))
        issues = [] if approved else [str(i) for i in data.get("issues", [])][:5]
        msg = "Approved the draft" if approved else f"Found {len(issues)} issues: {issues}"
    except Exception:
        approved, issues = True, []
        msg = "Could not parse the critic's reply; accepting the draft"
    return {
        "approved": approved,
        "issues": issues,
        "trace": _log(state, "critic", msg),
    }


def after_critic(state: State):
    if state["approved"] or state["drafts"] >= MAX_DRAFTS:
        return END
    return "writer"


def build_graph():
    g = StateGraph(State)
    g.add_node("planner", planner)
    g.add_node("retriever", retriever)
    g.add_node("writer", writer)
    g.add_node("critic", critic)
    g.add_edge(START, "planner")
    g.add_edge("planner", "retriever")
    g.add_edge("retriever", "writer")
    g.add_edge("writer", "critic")
    g.add_conditional_edges("critic", after_critic, {END: END, "writer": "writer"})
    return g.compile()


def run(goal: str):
    return build_graph().invoke(
        {
            "goal": goal,
            "plan": [],
            "evidence": [],
            "report": "",
            "issues": [],
            "approved": False,
            "drafts": 0,
            "trace": [],
        }
    )
def stream_run(goal: str):
    """Yield (agent_name, state_update) as each agent finishes."""
    graph = build_graph()
    initial = {
        "goal": goal,
        "plan": [],
        "evidence": [],
        "report": "",
        "issues": [],
        "approved": False,
        "drafts": 0,
        "trace": [],
    }
    for update in graph.stream(initial, stream_mode="updates"):
        for node, delta in update.items():
            yield node, delta    