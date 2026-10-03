import json
import re
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.llm import generate
from app.tools.retriever import search
from app.tools.web import web_search

MAX_DRAFTS = 3  # guardrail: the writer/critic loop stops after this many drafts


class State(TypedDict):
    goal: str
    plan: list[dict]
    evidence: list[dict]
    analysis: str
    report: str
    issues: list[str]
    approved: bool
    drafts: int
    trace: list[dict]


def _log(state, agent, message):
    return state["trace"] + [{"agent": agent, "message": message}]


def _evidence_text(state):
    return "\n\n".join(f"[{e['label']}] {e['text']}" for e in state["evidence"])


PLAN_PROMPT = """Break the goal into 2 to 4 short, specific questions.
For each, choose the source:
- "docs": can be answered from the user's uploaded documents
- "web": needs outside or current information that the documents would not contain
Return ONLY a JSON array like [{{"q": "question", "source": "docs"}}], with no other text.

GOAL: {goal}"""

ANALYST_PROMPT = """You are a data analyst. Using ONLY the evidence below, prepare notes for a report writer.
- List the key findings that answer the goal, each with a citation like [file p.3] or [web: example.com].
- Note any comparisons, numbers, or patterns (do arithmetic carefully and show it).
- List gaps: what the evidence does not cover. Do not invent facts.
Keep it under 300 words.

GOAL: {goal}

EVIDENCE:
{evidence}
"""

WRITE_PROMPT = """Write a clear report that achieves the goal, using ONLY the evidence and analysis below.
- Cite each claim like [file p.3] for documents or [web: example.com] for web sources.
- If the evidence is not enough, say what is missing. Do not invent facts.

GOAL: {goal}

ANALYSIS NOTES:
{analysis}

EVIDENCE:
{evidence}
"""

REVISE_PROMPT = """Revise the report below to fix every issue listed.
Use ONLY the evidence. Cite each claim like [file p.3] or [web: example.com]. Do not invent facts.
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
malformed citations (they must look like [file p.3] or [web: example.com]), and important gaps.
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
        items = json.loads(match.group(0))
        plan = []
        for it in items[:4]:
            if isinstance(it, dict):
                q = str(it.get("q", "")).strip()
                src = "web" if it.get("source") == "web" else "docs"
            else:
                q, src = str(it).strip(), "docs"
            if q:
                plan.append({"q": q, "source": src})
        if not plan:
            raise ValueError("empty plan")
    except Exception:
        plan = [{"q": state["goal"], "source": "docs"}]
    summary = "; ".join(f"({p['source']}) {p['q']}" for p in plan)
    return {
        "plan": plan,
        "trace": _log(state, "planner", f"Created {len(plan)} sub-questions: {summary}"),
    }


def retriever(state: State):
    seen, unique = set(), []
    for item in state["plan"]:
        if item["source"] != "docs":
            continue
        for c in search(item["q"], k=3):
            key = c["text"][:120]  # also removes duplicate uploads of the same file
            if key in seen:
                continue
            seen.add(key)
            unique.append(
                {
                    **c,
                    "kind": "doc",
                    "label": f"{c['file']} p.{c['page']}",
                    "question": item["q"],
                }
            )
    return {
        "evidence": unique,
        "trace": _log(state, "retriever", f"Found {len(unique)} unique passages in your documents"),
    }


def web_researcher(state: State):
    questions = [p["q"] for p in state["plan"] if p["source"] == "web"]
    if not questions:
        return {"trace": _log(state, "web_researcher", "No web questions in the plan; skipped")}
    found = list(state["evidence"])
    seen_urls = {e.get("url") for e in found if e.get("url")}
    added = 0
    for q in questions:
        for r in web_search(q, k=3):
            if r["url"] in seen_urls:
                continue
            seen_urls.add(r["url"])
            found.append({**r, "kind": "web", "question": q})
            added += 1
    return {
        "evidence": found,
        "trace": _log(
            state,
            "web_researcher",
            f"Searched the web for {len(questions)} question(s); kept {added} results",
        ),
    }


def analyst(state: State):
    if not state["evidence"]:
        return {"analysis": "", "trace": _log(state, "analyst", "No evidence to analyze")}
    analysis = generate(
        ANALYST_PROMPT.format(goal=state["goal"], evidence=_evidence_text(state))
    )
    return {"analysis": analysis, "trace": _log(state, "analyst", "Prepared analysis notes")}


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
        prompt = WRITE_PROMPT.format(
            goal=state["goal"], analysis=state["analysis"] or "(none)", evidence=evidence
        )
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
    g.add_node("web_researcher", web_researcher)
    g.add_node("analyst", analyst)
    g.add_node("writer", writer)
    g.add_node("critic", critic)
    g.add_edge(START, "planner")
    g.add_edge("planner", "retriever")
    g.add_edge("retriever", "web_researcher")
    g.add_edge("web_researcher", "analyst")
    g.add_edge("analyst", "writer")
    g.add_edge("writer", "critic")
    g.add_conditional_edges("critic", after_critic, {END: END, "writer": "writer"})
    return g.compile()


def _initial(goal: str):
    return {
        "goal": goal,
        "plan": [],
        "evidence": [],
        "analysis": "",
        "report": "",
        "issues": [],
        "approved": False,
        "drafts": 0,
        "trace": [],
    }


def run(goal: str):
    return build_graph().invoke(_initial(goal))


def stream_run(goal: str):
    """Yield (agent_name, state_update) as each agent finishes."""
    for update in build_graph().stream(_initial(goal), stream_mode="updates"):
        for node, delta in update.items():
            yield node, delta