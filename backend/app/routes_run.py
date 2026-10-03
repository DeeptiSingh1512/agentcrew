import json
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.agents.graph import create_plan, stream_run
from app.history import get_run, list_runs, save_run

router = APIRouter()


class PlanItem(BaseModel):
    q: str = Field(min_length=3, max_length=300)
    source: Literal["docs", "web"] = "docs"


class PlanRequest(BaseModel):
    goal: str = Field(min_length=3, max_length=500)


class RunRequest(BaseModel):
    goal: str = Field(min_length=3, max_length=500)
    plan: list[PlanItem] | None = Field(default=None, max_length=4)


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


def _events(goal: str, plan):
    final = {}
    try:
        for agent, delta in stream_run(goal, plan):
            final.update(delta)
            message = delta["trace"][-1]["message"] if delta.get("trace") else ""
            yield _sse({"type": "step", "agent": agent, "message": message})
        run_id = save_run(
            {
                "goal": goal,
                "plan": plan or final.get("plan", []),
                "report": final.get("report", ""),
                "approved": final.get("approved", False),
                "drafts": final.get("drafts", 0),
                "evidence": final.get("evidence", []),
                "trace": final.get("trace", []),
            }
        )
        yield _sse(
            {
                "type": "done",
                "report": final.get("report", ""),
                "approved": final.get("approved", False),
                "drafts": final.get("drafts", 0),
                "evidence": final.get("evidence", []),
                "run_id": run_id,
            }
        )
    except Exception as e:
        yield _sse({"type": "error", "message": str(e)})


@router.post("/plan")
def make_plan(req: PlanRequest):
    try:
        return {"plan": create_plan(req.goal)}
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/run")
def run_crew(req: RunRequest):
    plan = [p.model_dump() for p in req.plan] if req.plan else None
    return StreamingResponse(_events(req.goal, plan), media_type="text/event-stream")


@router.get("/history")
def history():
    try:
        return {"runs": list_runs()}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"History unavailable: {e}")


@router.get("/history/{run_id}")
def history_item(run_id: str):
    try:
        run = get_run(run_id)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"History unavailable: {e}")
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run